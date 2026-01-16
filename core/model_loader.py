"""
Osobny proces do ladowania modeli OpenVINO.
Uruchamiany przez subprocess - mozna go zabic w dowolnym momencie.
"""
import sys
import json
import traceback

def load_openvino_model(model_path: str, device: str) -> dict:
    """Laduje model OpenVINO i zwraca status."""
    try:
        print(f"[LOADER] Importing openvino_genai...", flush=True)
        import openvino_genai as ov_genai

        print(f"[LOADER] Loading model: {model_path}", flush=True)
        print(f"[LOADER] Device: {device}", flush=True)
        print(f"[LOADER] Creating WhisperPipeline...", flush=True)

        # Ta operacja moze trwac 1-2 minuty
        pipeline = ov_genai.WhisperPipeline(model_path, device)

        print("[LOADER] Model loaded successfully!", flush=True)
        return {"success": True, "error": None}

    except Exception as e:
        print(f"[LOADER] Error: {e}", flush=True)
        print(f"[LOADER] Traceback: {traceback.format_exc()}", flush=True)
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    print(f"[LOADER] Started with args: {sys.argv}", flush=True)

    if len(sys.argv) != 3:
        result = {"success": False, "error": "Usage: model_loader.py <model_path> <device>"}
        print(f"RESULT:{json.dumps(result)}", flush=True)
        sys.exit(1)

    model_path = sys.argv[1]
    device = sys.argv[2]

    try:
        result = load_openvino_model(model_path, device)
    except Exception as e:
        print(f"[LOADER] Fatal error: {e}", flush=True)
        print(f"[LOADER] Traceback: {traceback.format_exc()}", flush=True)
        result = {"success": False, "error": str(e)}

    # Wypisz JSON na stdout
    print(f"RESULT:{json.dumps(result)}", flush=True)
    sys.exit(0 if result["success"] else 1)
