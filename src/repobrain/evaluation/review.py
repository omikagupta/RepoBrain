from collections.abc import Sequence
from pathlib import Path
from urllib.parse import quote

from repobrain.evaluation.dataset import Question


def write_review(path: Path, questions: Sequence[Question]) -> None:
    with path.open("x", encoding="utf-8") as output:
        output.write("# Annotation review\n\n")
        output.write(
            "Check each expected answer and span against the pinned source. "
            "Record corrections in a new dataset version after a freeze.\n"
        )
        for item in questions:
            output.write(
                f"\n## {item.question_id}\n\n"
                f"{item.question}\n\n{item.repository} · `{item.commit_sha}` · "
                f"{item.category} · {item.annotation_status}\n\n"
                f"{item.expected_answer}\n\n{item.annotation_rationale}\n"
            )
            for point in item.required_answer_points:
                output.write(f"\n- Required point — {point}")
            output.write("\n")
            for label in item.relevant_evidence:
                link = (
                    f"https://github.com/{item.repository}/blob/{item.commit_sha}/"
                    f"{quote(label.path)}#L{label.start_line}-L{label.end_line}"
                )
                output.write(
                    f"\n- [`{label.path}` {label.start_line}–{label.end_line}]({link})"
                    f" · grade {label.relevance_grade} · {label.evidence_group}"
                    f" — {label.rationale}"
                )
            output.write("\n\n- [ ] Independently reviewed\n")
