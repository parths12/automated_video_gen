# Illustrator Agent — Manim Code Generation

## Purpose

The Illustrator Agent converts the `StoryArc` into executable **Manim Community Edition (ManimCE)** Python code. This is technically the most complex agent because:

1. Manim code is extremely sensitive to syntax and API version
2. The LLM tends to use outdated Manim APIs or hallucinate methods
3. Layout positioning requires precise coordinate math
4. The code must execute without errors to produce a video

**File location:** `agents/illustrator.py`

---

## Manim Setup

### Install

```bash
pip install manim
# Also requires system dependencies:
# macOS: brew install cairo pango ffmpeg
# Ubuntu: sudo apt install libcairo2-dev libpango1.0-dev ffmpeg
# Windows: use the Windows installer from manim.community
```

### Verify Installation

```bash
manim --version
# Should print: Manim Community v0.18.x
```

### Key Manim Concepts the LLM Must Know

Before generating code, the system prompt must teach the LLM these essentials:

**Coordinate system:**
- Scene is 14 units wide × 8 units tall
- Center is (0, 0)
- Right edge ≈ x=7, Left edge ≈ x=-7
- Top ≈ y=4, Bottom ≈ y=-4
- `UP = [0, 1, 0]`, `DOWN = [0, -1, 0]`, `LEFT = [-1, 0, 0]`, `RIGHT = [1, 0, 0]`

**Most-used objects for NCERT math:**
- `MathTex("ax + b = c")` — renders LaTeX math
- `Text("plain text")` — renders normal text
- `NumberLine(x_range=[-5, 5, 1])` — number line
- `Axes(x_range=[-3, 3], y_range=[-3, 3])` — coordinate axes
- `FunctionGraph(lambda x: x**2)` — plot a function
- `Arrow(start, end)` — directional arrow
- `Rectangle(width=3, height=2)` — rectangle
- `Circle(radius=1)` — circle
- `VGroup(obj1, obj2)` — group objects
- `DecimalNumber(value)` — animated number

**Common animations:**
- `self.play(Write(text))` — write text
- `self.play(Create(shape))` — draw a shape
- `self.play(Transform(a, b))` — morph one object into another
- `self.play(FadeIn(obj))`, `self.play(FadeOut(obj))`
- `self.play(obj.animate.shift(RIGHT * 2))` — move
- `self.play(obj.animate.scale(1.5))` — scale
- `self.wait(1)` — pause for 1 second

---

## Implementation

```python
# agents/illustrator.py

import json
import subprocess
import tempfile
import os
from pathlib import Path
from utils.schemas import StoryArc, ConceptCard, HookSpec, ManimCode
from utils.llm_client import call_llm
from pydantic import ValidationError


ILLUSTRATOR_SYSTEM_PROMPT = """You are an expert Manim Community Edition (ManimCE v0.18) developer.
You write Python code that produces beautiful, clear mathematical animations.

CRITICAL RULES — violating these will cause render errors:
1. Use ONLY ManimCE v0.18 API. Do NOT use deprecated methods.
2. Never use: ShowCreation (use Create), ShowPassingFlash (use Create with run_time)
3. Always import: from manim import *
4. The scene class MUST be named VideoScene and inherit from Scene
5. All math text uses MathTex, NOT Tex or TeX
6. Positions use numpy arrays or Manim constants (UP, DOWN, LEFT, RIGHT, ORIGIN)
7. Never place two objects at the same position — they will overlap
8. Text that appears together must be arranged with .arrange() or explicit .shift()
9. Always call self.clear() or self.play(FadeOut(*self.mobjects)) between major scene transitions
10. End the construct() method with self.wait(2)

LAYOUT RULES:
- Scene is 14 units wide, 8 units tall. Center is (0,0).
- Title area: y = 3 to 4 (top)
- Main animation area: y = -2 to 2.5 (center)
- Subtitle/caption area: y = -3 to -3.5 (bottom)
- Never place objects beyond x=±6.5 or y=±3.8

ANIMATION PRINCIPLES (3Blue1Brown style):
- Reveal information progressively — never show everything at once
- Use Transform() to show algebraic steps (equation morphs to next form)
- Use pause-and-reveal: animate silently first, then add the label
- Color-code: equations in WHITE, highlights in YELLOW, answers in GREEN
- Use slow animations (run_time=2) for important steps

You must return ONLY valid JSON with the ManimCode schema. The 'code' field is the complete Python file content."""


ANCHOR_GRID_EXPLANATION = """
POSITIONING GUIDE — use these anchor positions for consistent layout:
TOP_LEFT     = np.array([-5.5,  3.0, 0])
TOP_CENTER   = np.array([ 0.0,  3.0, 0])
TOP_RIGHT    = np.array([ 5.5,  3.0, 0])
MID_LEFT     = np.array([-5.5,  0.5, 0])
MID_CENTER   = np.array([ 0.0,  0.5, 0])
MID_RIGHT    = np.array([ 5.5,  0.5, 0])
BOT_LEFT     = np.array([-5.5, -2.5, 0])
BOT_CENTER   = np.array([ 0.0, -2.5, 0])
BOT_RIGHT    = np.array([ 5.5, -2.5, 0])
CAPTION      = np.array([ 0.0, -3.3, 0])

Use these as starting points, then adjust with .shift() as needed.
"""


def build_illustrator_prompt(
    story_arc: StoryArc,
    concept_card: ConceptCard,
    hook_spec: HookSpec,
    schema_str: str,
    error_feedback: str = ""
) -> str:
    """
    Builds the prompt for the illustrator agent.
    error_feedback is populated on retry attempts with the Manim error message.
    """
    scenes_str = "\n\n".join([
        f"--- SCENE {s.scene_number}: {s.title} ({s.duration_seconds}s) ---\n"
        f"Narration: {s.narration}\n"
        f"Animation to show: {s.animation_description}\n"
        f"Manim hint: {s.manim_hint}\n"
        f"Reveals formula: {s.reveals_formula}"
        for s in story_arc.scenes
    ])
    
    error_section = ""
    if error_feedback:
        error_section = f"""
PREVIOUS ATTEMPT FAILED WITH THIS ERROR:
{error_feedback}

Fix the error. The most common causes are:
- Using deprecated Manim API (ShowCreation → Create, etc.)
- Objects placed outside the viewable area (beyond x=±6.5, y=±3.8)
- Missing import statements
- Calling methods that don't exist on the object type
- Two objects overlapping because .arrange() was not used
"""
    
    return f"""Generate Manim Python code for this educational video.

TOPIC: {story_arc.topic} (Class {story_arc.grade})
CORE ANALOGY: {hook_spec.analogy}
OPENING VISUAL: {hook_spec.visual_action}
KEY EQUATIONS (LaTeX): {concept_card.latex_equations}
COMMON STUDENT ERRORS (make these visually obvious when showing wrong approaches): {concept_card.common_errors}

{ANCHOR_GRID_EXPLANATION}

VIDEO SCENES TO ANIMATE:
{scenes_str}

IMPORTANT SCENE RULE:
- Scene 1 animates the ANALOGY ({hook_spec.analogy}), NOT the formula
- The first MathTex equation appears in scene {_find_formula_scene(story_arc)}

{error_section}

Return JSON matching this schema:
{schema_str}

The 'code' field must be a COMPLETE, RUNNABLE Python file.
It must start with: from manim import *
It must contain exactly ONE class named VideoScene(Scene)."""


def _find_formula_scene(arc: StoryArc) -> int:
    """Returns the scene number where the formula first appears."""
    for scene in arc.scenes:
        if scene.reveals_formula:
            return scene.scene_number
    return 2  # default to scene 2


def generate_manim_code(
    story_arc: StoryArc,
    concept_card: ConceptCard,
    hook_spec: HookSpec,
    max_retries: int = 3
) -> ManimCode:
    """
    Generates and validates Manim code. Auto-retries up to max_retries times
    if the code fails to execute.
    
    Args:
        story_arc: the planned video structure
        concept_card: the concept being explained
        hook_spec: the creative hook
        max_retries: how many times to retry on error
        
    Returns:
        validated ManimCode that successfully renders
    """
    schema_str = json.dumps(ManimCode.model_json_schema(), indent=2)
    error_feedback = ""
    
    for attempt in range(1, max_retries + 1):
        print(f"[Illustrator] Attempt {attempt}/{max_retries}...")
        
        prompt = build_illustrator_prompt(
            story_arc, concept_card, hook_spec, schema_str, error_feedback
        )
        
        response = call_llm(
            system_prompt=ILLUSTRATOR_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=6000,
            temperature=0.2    # low temp for code generation
        )
        
        # Parse JSON
        try:
            code_data = json.loads(response)
            manim_code = ManimCode.model_validate(code_data)
        except (json.JSONDecodeError, ValidationError) as e:
            error_feedback = f"JSON parsing error: {e}"
            print(f"[Illustrator] JSON error on attempt {attempt}: {e}")
            continue
        
        # Validate by dry-running the code
        syntax_error = _check_python_syntax(manim_code.code)
        if syntax_error:
            error_feedback = f"Python syntax error: {syntax_error}"
            print(f"[Illustrator] Syntax error on attempt {attempt}: {syntax_error}")
            continue
        
        print(f"[Illustrator] Code generated successfully ({len(manim_code.code)} chars)")
        return manim_code
    
    raise RuntimeError(f"Illustrator failed after {max_retries} attempts. Last error: {error_feedback}")


def _check_python_syntax(code: str) -> str | None:
    """
    Checks if the code has valid Python syntax.
    Returns error message string if invalid, None if valid.
    """
    try:
        compile(code, "<string>", "exec")
        return None
    except SyntaxError as e:
        return f"Line {e.lineno}: {e.msg}"


def save_manim_code(manim_code: ManimCode, output_path: str) -> str:
    """Saves the Manim code to a .py file. Returns the file path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(manim_code.code)
    
    print(f"[Illustrator] Saved Manim code to {output_path}")
    return str(output_path)
```

---

## renderer.py — Executing the Manim Code

**File location:** `render/renderer.py`

```python
# render/renderer.py

import subprocess
import os
from pathlib import Path


def render_video(
    manim_file_path: str,
    scene_class: str = "VideoScene",
    output_dir: str = "outputs/",
    quality: str = "medium_quality"    # low_quality, medium_quality, high_quality
) -> str:
    """
    Executes Manim to render the Python file into an MP4.
    
    Quality options:
    - low_quality:    480p 15fps (fast, for testing)
    - medium_quality: 720p 30fps (good for Shorts)
    - high_quality:   1080p 60fps (production, slow)
    
    Args:
        manim_file_path: path to the .py file
        scene_class: name of the Scene class (always "VideoScene")
        output_dir: where to save the rendered MP4
        quality: render quality preset
        
    Returns:
        path to the rendered MP4 file
    """
    manim_file = Path(manim_file_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    quality_flag = {
        "low_quality": "-ql",
        "medium_quality": "-qm",
        "high_quality": "-qh"
    }.get(quality, "-qm")
    
    cmd = [
        "manim",
        quality_flag,
        str(manim_file),
        scene_class,
        "--output_file", manim_file.stem,
        "--media_dir", str(output_dir)
    ]
    
    print(f"[Renderer] Running: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(
            f"Manim render failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    
    # Find the output file (Manim puts it in a subdirectory)
    video_files = list(output_dir.rglob("*.mp4"))
    if not video_files:
        raise FileNotFoundError(f"Manim rendered successfully but no MP4 found in {output_dir}")
    
    # Return the most recently created MP4
    latest = max(video_files, key=os.path.getmtime)
    print(f"[Renderer] Video rendered: {latest}")
    return str(latest)
```

---

## Example Manim Code the LLM Should Produce

This is an example of what GOOD Manim code looks like for the "Linear Equations — Balance Scale" analogy. Use this as a few-shot example in the illustrator prompt if output quality is poor.

```python
# Example: good Manim code for linear equation balance scale analogy

from manim import *

class VideoScene(Scene):
    def construct(self):
        # ── SCENE 1: Balance scale analogy (0–20s) ──────────────────────
        
        # Draw balance scale
        fulcrum = Triangle(fill_color=GRAY, fill_opacity=1).scale(0.3).move_to(DOWN * 1.5)
        beam = Line(LEFT * 3, RIGHT * 3).move_to(UP * 0)
        left_pan = Rectangle(width=2, height=0.1, color=BLUE).move_to(LEFT * 3 + DOWN * 0.5)
        right_pan = Rectangle(width=2, height=0.1, color=BLUE).move_to(RIGHT * 3 + DOWN * 0.5)
        left_string = Line(LEFT * 3, LEFT * 3 + DOWN * 0.5, color=GRAY)
        right_string = Line(RIGHT * 3, RIGHT * 3 + DOWN * 0.5, color=GRAY)
        
        scale = VGroup(fulcrum, beam, left_pan, right_pan, left_string, right_string)
        
        self.play(Create(scale), run_time=2)
        self.wait(0.5)
        
        # Add weights to left pan: 2x + 3
        left_label = MathTex("2x + 3", color=YELLOW).move_to(LEFT * 3 + UP * 0.5)
        right_label = MathTex("11", color=YELLOW).move_to(RIGHT * 3 + UP * 0.5)
        
        self.play(Write(left_label), Write(right_label), run_time=1.5)
        self.wait(1)
        
        # Caption
        caption = Text("Both sides must stay equal", font_size=28, color=WHITE).move_to(DOWN * 3.2)
        self.play(FadeIn(caption))
        self.wait(2)
        
        # ── SCENE 2: Show the equation (20–40s) ─────────────────────────
        
        self.play(FadeOut(caption), FadeOut(scale), FadeOut(left_label), FadeOut(right_label))
        self.wait(0.5)
        
        # Start equation
        eq1 = MathTex("2x", "+", "3", "=", "11").scale(1.3).move_to(UP * 1)
        self.play(Write(eq1), run_time=1.5)
        self.wait(0.5)
        
        # Step 1: subtract 3 from both sides
        step1_text = Text("Subtract 3 from both sides", font_size=28, color=GRAY).move_to(DOWN * 0.5)
        self.play(FadeIn(step1_text))
        self.wait(0.5)
        
        eq2 = MathTex("2x", "=", "8").scale(1.3).move_to(UP * 1)
        self.play(Transform(eq1, eq2), run_time=1.5)
        self.wait(0.5)
        
        # Step 2: divide both sides by 2
        step2_text = Text("Divide both sides by 2", font_size=28, color=GRAY).move_to(DOWN * 0.5)
        self.play(Transform(step1_text, step2_text))
        self.wait(0.5)
        
        eq3 = MathTex("x", "=", "4").scale(1.8).move_to(UP * 1)
        self.play(Transform(eq1, eq3), run_time=1.5)
        
        # Highlight answer
        box = SurroundingRectangle(eq3, color=GREEN, buff=0.3)
        self.play(Create(box), run_time=1)
        self.wait(2)
        
        # ── SCENE 3: Real-world resolution (40–65s) ─────────────────────
        
        self.play(FadeOut(eq1), FadeOut(eq3), FadeOut(box), FadeOut(step2_text))
        
        riya_text = Text("Riya: ₹200 + ₹50 × 4 weeks = ₹400", font_size=28, color=BLUE).move_to(UP * 0.8)
        priya_text = Text("Priya: ₹80 + ₹80 × 4 weeks = ₹400", font_size=28, color=CORAL).move_to(DOWN * 0.2)
        equal_text = Text("Equal after 4 weeks!", font_size=32, color=GREEN).move_to(DOWN * 1.4)
        
        self.play(Write(riya_text), run_time=1.5)
        self.wait(0.5)
        self.play(Write(priya_text), run_time=1.5)
        self.wait(0.5)
        self.play(FadeIn(equal_text))
        self.wait(2)
        
        self.wait(2)  # always end with a wait
```

---

## Common Manim Errors and Fixes

| Error | Cause | Fix |
|---|---|---|
| `AttributeError: 'Scene' has no 'ShowCreation'` | Deprecated API | Replace with `Create()` |
| `ValueError: math domain error` | Division by zero in function | Add domain check in lambda |
| Objects appearing off-screen | Coordinates too large | Check all positions stay within x=±6.5, y=±3.8 |
| Text overlapping | Two `Write()` calls to same position | Use `.next_to()` or `.arrange()` |
| `TypeError: MathTex() got unexpected keyword argument 'tex_template'` | Wrong API | Remove `tex_template` argument |
| Video is just black | Scene class name mismatch | Ensure class is named `VideoScene` |
| `ModuleNotFoundError: No module named 'manim'` | Not installed in active venv | `pip install manim` in correct environment |

---

## Testing the Illustrator

```python
# test_illustrator.py

import json
from pathlib import Path
from agents.illustrator import generate_manim_code, save_manim_code
from render.renderer import render_video
from utils.schemas import StoryArc, ConceptCard, HookSpec

# Load previously generated outputs
with open("test_outputs/story_arc.json") as f:
    arc = StoryArc.model_validate_json(f.read())
with open("data/concept_cards/class8_ch2/class8_solving_equations.json") as f:
    card = ConceptCard.model_validate_json(f.read())
with open("test_outputs/hook_spec.json") as f:
    hook = HookSpec.model_validate_json(f.read())

# Generate Manim code
print("Generating Manim code...")
manim_code = generate_manim_code(arc, card, hook, max_retries=3)

# Save to file
code_path = save_manim_code(manim_code, "test_outputs/video_scene.py")

# Render (use low quality for testing — much faster)
print("Rendering video...")
video_path = render_video(
    code_path,
    quality="low_quality",
    output_dir="test_outputs/"
)
print(f"Video saved to: {video_path}")
```
