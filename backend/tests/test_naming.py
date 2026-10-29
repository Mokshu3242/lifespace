"""Naming: printed text wins, models vote, a referee settles splits, sizes need two readers."""
import numpy as np

from app.space import naming, ocr
from app.space.ocr import Text, name_from_pieces, split_words


def test_split_and_join_printed_names():
    assert split_words("SECONDBEDROOM") == "second bedroom"
    assert split_words("LIVINGROOM") == "living room"
    pieces = lambda *xs: [Text(x, 0, i, 1, False) for i, x in enumerate(xs)]
    assert name_from_pieces(pieces("BATHROOM", "MASTER")) == "Master Bathroom"
    assert name_from_pieces(pieces("CL")) == "Closet"
    assert name_from_pieces(pieces("LC")) == "Linen Closet"
    assert name_from_pieces(pieces("WC")) == "WC"
    assert name_from_pieces(pieces("Built-in")) == "Built-In"


def test_same_name_rules():
    assert naming._same("Bedroom", "Master Bedroom")
    assert naming._same("Restroom", "Bathroom")
    assert not naming._same("Bedroom", "Office")


def _setup(monkeypatch, texts, votes, referee=None):
    """Three spaces side by side; fake OCR and fake models."""
    regions = np.full((30, 90), -1, np.int32)
    regions[:, 0:30], regions[:, 30:60], regions[:, 60:90] = 0, 1, 2
    marks = [(15, 15), (45, 15), (75, 15)]
    monkeypatch.setattr(ocr, "read_texts", lambda gray: texts)
    monkeypatch.setattr(naming, "draw_sheets",
                        lambda gray, marks, regions, only: [(b"png", only)] if only else [])

    class R:
        asked = []

        def see_each(self, prompt, png):
            return votes

        def ask_json(self, prompt):
            R.asked.append(prompt)
            if referee is None:
                raise RuntimeError("no text model")
            return referee

    return marks, regions, R


def test_printed_wins_and_models_vote(monkeypatch):
    texts = [Text("SECONDBEDROOM", 15, 10, 0.9, False), Text("10'10\" x 14'7\"", 15, 20, 0.8, True)]
    votes = {
        "cloudflare": {"tiles": [{"id": 2, "name": "Office", "reason": "desk and chair"},
                                 {"id": 3, "name": "Lounge", "reason": "sofa"}]},
        "ollama": {"tiles": [{"id": 2, "name": "Office", "reason": "a desk"},
                             {"id": 3, "name": "Bathroom", "reason": "oval shape"}]},
        "groq": {"tiles": [{"id": 2, "name": "Bedroom", "reason": "rectangle"},
                           {"id": 3, "name": "Lounge", "reason": "sofa and coffee table"}]},
    }
    marks, regions, R = _setup(monkeypatch, texts, votes)
    labels = naming.name_spaces(np.zeros((30, 90), np.uint8), marks, regions, R())
    assert (labels[0].name, labels[0].source, labels[0].dims) == ("Second Bedroom", "printed", "10'10\" x 14'7\"")
    assert (labels[1].name, labels[1].source) == ("Office", "majority")
    assert (labels[2].name, labels[2].source, labels[2].unsure) == ("Lounge", "majority", False)
    assert R.asked == []      # no referee needed


def test_referee_settles_a_split_and_flags_it(monkeypatch):
    votes = {"cloudflare": {"tiles": [{"id": k, "name": "Lounge", "reason": "sofa"} for k in (1, 2, 3)]},
             "ollama": {"tiles": [{"id": k, "name": "Bathroom", "reason": "oval"} for k in (1, 2, 3)]}}
    marks, regions, R = _setup(monkeypatch, [], votes,
                               referee={"decisions": [{"id": 1, "name": "Lounge", "reason": "sofa is specific"}]})
    labels = naming.name_spaces(np.zeros((30, 90), np.uint8), marks, regions, R())
    assert (labels[0].name, labels[0].source, labels[0].unsure) == ("Lounge", "referee", True)
    assert labels[1].name == "Lounge"          # referee skipped it: first model's answer kept
    assert len(R.asked) == 1                   # one referee call for all splits


def test_model_sizes_need_two_matching_readers(monkeypatch):
    votes = {"a": {"tiles": [{"id": 1, "name": "Den", "dims": "10'0\" x 12'0\""}]},
             "b": {"tiles": [{"id": 1, "name": "Den", "dims": "14'0\" x 12'0\""}]}}
    marks, regions, R = _setup(monkeypatch, [], votes)
    labels = naming.name_spaces(np.zeros((30, 90), np.uint8), marks, regions, R())
    assert labels[0].dims == ""                # they disagree, so no size
    assert labels[1].name == "Space 2" and labels[1].unsure


def test_context_line_tells_models_the_space_type():
    from app.space.reader import NAME_PROMPT, context_line
    line = context_line("office", "tech startup office")
    assert "office (tech startup office)" in line and "meeting room" in line
    assert "bedroom" not in line
    assert context_line("castle").startswith("This plan is a home.")      # unknown pack falls back
    assert NAME_PROMPT.format(context=line, ids="1").startswith("This plan is an office")
