from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "diagrams"
DEFAULT_MERMAID_PATH = DEFAULT_OUTPUT_DIR / "agent_workflow_flow.mmd"
DEFAULT_PNG_PATH = DEFAULT_OUTPUT_DIR / "agent_workflow_flow.png"


def build_mermaid_diagram() -> str:
    return """flowchart TD
    A[API Request<br>/api/tasks] --> B[TaskRequest validation]
    B --> C{Input complete?}
    C -- No --> D[Return needs_clarification<br>Save checkpoint]
    C -- Yes --> E[Load latest checkpoint]
    E --> F{Existing workflow?}
    F -- Waiting for approval or terminal --> G[Return persisted response]
    F -- Active workflow --> H[Continue workflow delegation]
    F -- None --> I[Supervisor planning]

    I --> J{APP_AI_MODE=live<br>and OPENAI key present?}
    J -- No --> K[Fallback plan builder]
    J -- Yes --> L[DeepAgents Supervisor]
    K --> M[Sort plan steps]
    L --> M

    M --> N[Save checkpoint: plan_created]
    N --> H

    H --> O[Delegate ready steps]
    O --> P[STEP-1 Deployment analysis]
    O --> Q[STEP-2 Infrastructure analysis]
    O --> R[STEP-3 CI/CD analysis]

    P --> S{Operation type}
    Q --> S
    R --> S

    S -- deploy rollback restart --> T[STEP-4 Service rollout]
    S -- scale configure --> U[STEP-4 Environment change]
    S -- pipeline build test release --> V[STEP-4 Pipeline procedure]
    S -- other --> W[STEP-4 Diagnostic plan]

    T --> X[STEP-5 Risk and policy review]
    U --> X
    V --> X
    W --> X

    X --> Y{Approval required?}
    Y -- Yes --> Z[STEP-6 Human approval]
    Y -- No --> AA[STEP-6 or STEP-7 Execution handoff]
    Z --> AB{Approved?}
    AB -- No --> AC[Workflow blocked or rejected<br>Save checkpoint]
    AB -- Yes --> AA

    AA --> AD[STEP-7 or STEP-8 Final report]
    AD --> AE[Aggregate result state]
    AE --> AF[Save checkpoint]
    AF --> AG[Return TaskResponse]

    O --> AH{Any missing input<br>or failed dependency?}
    AH -- Yes --> AI[Mark dependent steps blocked]
    AI --> AF
"""


def render_png(mermaid_path: Path, png_path: Path) -> bool:
    mermaid_cli = shutil.which("mmdc")
    if not mermaid_cli:
        return False

    subprocess.run(
        [mermaid_cli, "-i", str(mermaid_path), "-o", str(png_path)],
        check=True,
    )
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Mermaid agent workflow diagram and optional PNG output."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated Mermaid and PNG files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    mermaid_path = output_dir / DEFAULT_MERMAID_PATH.name
    png_path = output_dir / DEFAULT_PNG_PATH.name
    mermaid_path.write_text(build_mermaid_diagram(), encoding="utf-8")

    try:
        rendered = render_png(mermaid_path=mermaid_path, png_path=png_path)
    except subprocess.CalledProcessError as error:
        print(
            "Mermaid file saved, but PNG rendering failed via mmdc: "
            f"{error}",
            file=sys.stderr,
        )
        return 1

    if rendered:
        print(f"Generated Mermaid: {mermaid_path}")
        print(f"Generated PNG: {png_path}")
        return 0

    print(f"Generated Mermaid: {mermaid_path}")
    print("PNG not generated because `mmdc` is not installed.")
    print("Install Mermaid CLI and rerun:")
    print("  npm install -g @mermaid-js/mermaid-cli")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
