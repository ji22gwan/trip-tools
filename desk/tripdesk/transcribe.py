"""녹음 → 글. 노트북에서 faster-whisper 로 돌린다(선택 설치). 없으면 친절히 안내하고, 직접 입력도 가능하다."""
import threading

DEFAULT_MODEL = "small"
MODELS = ["tiny", "base", "small", "medium", "large-v3"]
LANGUAGES = {"ko": "한국어", "en": "영어", "de": "독일어", "auto": "자동 감지"}


class TranscribeError(Exception):
    pass


_backend = None  # 시험용: callable(path, language, prompt, model) -> str
_models: dict = {}
_lock = threading.Lock()


def set_backend(fn) -> None:
    global _backend
    _backend = fn


def available() -> tuple[bool, str]:
    if _backend:
        return True, ""
    try:
        import faster_whisper  # noqa: F401
        return True, ""
    except ImportError:
        return False, ("음성 인식 엔진(faster-whisper)이 설치되어 있지 않아요. install-desk 를 'WHISPER=1 ./install-desk.sh' 로 다시 실행하면 설치돼요. "
                       "설치하지 않아도 녹음 전사본을 직접 붙여 넣어 쓸 수 있어요.")


def transcribe_file(path, language: str = "ko", prompt: str = "", model: str = DEFAULT_MODEL) -> str:
    if _backend:
        return _backend(path, language, prompt, model)
    ok, why = available()
    if not ok:
        raise TranscribeError(why)
    from faster_whisper import WhisperModel

    with _lock:
        if model not in _models:
            try:
                _models[model] = WhisperModel(model, device="cpu", compute_type="int8")
            except Exception as e:  # noqa: BLE001 - 모델 내려받기 실패 등을 사용자 말로 바꾼다
                raise TranscribeError(f"음성 인식 모델('{model}')을 준비하지 못했어요. 처음 한 번은 인터넷이 필요해요: {e}") from e
        m = _models[model]
    try:
        segs, _info = m.transcribe(str(path), language=None if language == "auto" else language,
                                   initial_prompt=prompt or None, vad_filter=True, beam_size=5)
        return " ".join(s.text.strip() for s in segs).strip()
    except Exception as e:  # noqa: BLE001
        raise TranscribeError(f"전사 중 오류: {e}") from e


def run_day(visits: dict, state: dict, path_of, language: str, prompt: str, model: str, redo: bool, progress, save) -> tuple[int, list[str]]:
    """하루치 녹음을 차례로 전사한다. 이미 글이 있는 녹음은 redo=False 면 건너뛴다. 하나가 실패해도 나머지는 계속한다."""
    from .daily import recordings_of

    recs = recordings_of(visits)
    todo = [r for r in recs if redo or not state["recordings"].get(r["file"], {}).get("text")]
    done, errors = 0, []
    for i, r in enumerate(todo, start=1):
        progress(f"{i}/{len(todo)} 전사 중: {r['companyName']} {r['file'].split('/')[-1]}")
        try:
            text = transcribe_file(path_of(r["file"]), language, prompt, model)
        except TranscribeError as e:
            errors.append(f"{r['file'].split('/')[-1]}: {e}")
            if "설치" in str(e) or "모델" in str(e):
                break  # 엔진 자체가 없으면 나머지도 실패하므로 바로 멈춘다
            continue
        except FileNotFoundError:
            errors.append(f"{r['file'].split('/')[-1]}: 파일이 없어요")
            continue
        rec = state["recordings"].setdefault(r["file"], {})
        rec.update({"text": text, "engine": f"whisper-{model}", "language": language})
        if redo:
            rec.pop("corrected", None)
        save()
        done += 1
    return done, errors
