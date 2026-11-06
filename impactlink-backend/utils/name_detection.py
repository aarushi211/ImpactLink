"""Local English person-name detection; never downloads models during a request."""

from threading import RLock

MODEL = "en_core_web_sm"
_pipeline = None
_lock = RLock()


class PrivacyDetectionUnavailable(RuntimeError):
    pass


def ensure_name_detection():
    global _pipeline
    with _lock:
        if _pipeline is None:
            try:
                import spacy
                model = spacy.load(MODEL, exclude=["tagger", "parser", "attribute_ruler", "lemmatizer"])
                if "ner" not in model.pipe_names or not hasattr(model, "memory_zone"):
                    raise ValueError("Unsupported local name model")
                _pipeline = model
            except Exception:
                raise PrivacyDetectionUnavailable("Local name protection is unavailable. AI processing was stopped; please retry after the service is restored.") from None
        return _pipeline


def person_spans(text):
    model = ensure_name_detection()
    spans = set()
    # An overlap keeps names around chunk boundaries intact; no Doc escapes its memory zone.
    try:
        with _lock:
            for start in range(0, len(text), 16000):
                chunk = text[start:start + 16256]
                with model.memory_zone():
                    doc = model(chunk)
                    spans.update((start + item.start_char, start + item.end_char) for item in doc.ents if item.label_ == "PERSON")
    except Exception:
        raise PrivacyDetectionUnavailable("Local name protection failed. The AI request was stopped; retry after checking the backend model.") from None
    return sorted(spans)
