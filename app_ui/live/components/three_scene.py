from nicegui import ui, app
from typing import Optional, Dict
import asyncio
import json

class ThreeStage(ui.element):
    def __init__(self):
        super().__init__('div')
        self.classes('w-full h-full relative overflow-hidden')
        self._initialized = False
        self._init_ok: Optional[bool] = None
        print("[ThreeStage] __init__ called")

        # 1. Setup Import Map for Three.js (Module resolution)
        # Using local files downloaded by installer
        import_map = """
        <script type="importmap">
          {
            "imports": {
              "three": "/assets/js/three.module.js",
              "three/addons/renderers/CSS3DRenderer.js": "/assets/js/CSS3DRenderer.js",
              "three/addons/libs/tween.module.js": "/assets/js/tween.module.js"
            }
          }
        </script>
        """
        ui.add_head_html(import_map)

        # 2. Load our Engine
        # We will load it dynamically in _init_client_side to ensure order
        # ui.add_head_html('<script type="module" src="/assets/js/card_engine.js"></script>')

        # 3. Initialize on Client - use timer as fallback since mount event may not fire
        self.on('mount', self._init_client_side)
        # Fallback: try init after short delay
        ui.timer(1.0, self._init_client_side, once=True)

    async def _init_client_side(self):
        if self._initialized:
            print("[ThreeStage] Already initialized, skipping")
            return

        print(f"[ThreeStage] _init_client_side called, container id={self.id}")

        # Diagnostic: check if files are accessible and create engine
        js_init = f'''
        (async function() {{
            let diag = {{}};

            // Test if container exists (NiceGUI uses "c" prefix for element IDs)
            diag.containerExists = !!document.getElementById("c{self.id}");

            // Try to load the module
            try {{
                console.log("[3D] Starting dynamic import...");
                const module = await import('/assets/js/card_engine.js');
                console.log("[3D] Module loaded:", module);
                diag.moduleLoaded = true;
                diag.hasCreateCardEngine = !!module.createCardEngine;

                if (module.createCardEngine) {{
                    window.engine = module.createCardEngine("c{self.id}");
                    diag.engineCreated = !!window.engine;
                    console.log("[3D] Engine created:", window.engine);
                }}
            }} catch(e) {{
                diag.moduleLoaded = false;
                diag.error = e.message;
                console.error("[3D] Import error:", e);
            }}

            console.log("[3D-INIT]", JSON.stringify(diag));
            return JSON.stringify(diag);
        }})()
        '''
        try:
            result = await ui.run_javascript(js_init, timeout=15.0)
            print(f"[ThreeStage] Init diagnostic: {result}")
            try:
                if isinstance(result, dict):
                    diag = result
                else:
                    diag = json.loads(result) if result else {}
                self._init_ok = bool(diag.get("engineCreated"))
            except Exception:
                self._init_ok = None
        except Exception as e:
            print(f"[ThreeStage] Init error: {e}")
            self._init_ok = None

        self._initialized = True
        print("[ThreeStage] Initialization complete, _initialized=True")

    def is_ready(self) -> bool:
        """Returns True when JS engine initialized correctly."""
        return bool(self._init_ok)

    async def probe_ready(self) -> bool:
        """Probe for engine readiness if init timing out."""
        probe_js = '''
        (function() {
            const ok = !!(window.engine && typeof window.engine.addCard === 'function');
            return JSON.stringify({engineExists: ok});
        })()
        '''
        try:
            result = await ui.run_javascript(probe_js, timeout=5.0)
            if isinstance(result, dict):
                diag = result
            else:
                diag = json.loads(result) if result else {}
            self._init_ok = bool(diag.get("engineExists"))
        except Exception:
            # Leave as None if still inconclusive
            if self._init_ok is not True:
                self._init_ok = None
        return bool(self._init_ok)

    async def run_method_js(self, code: str):
        """Helper to run JS safely."""
        try:
            await ui.run_javascript(code, timeout=10.0)
        except Exception as e:
            print(f"[ThreeStage] JS error: {e}")

    async def add_card(self, card_element: ui.element):
        """
        Takes a NiceGUI element (the card), ensures it's mounted,
        and passes its ID to the 3D engine.
        """
        print(f"[ThreeStage] add_card called for element c{card_element.id}")

        # Wait for init
        wait_count = 0
        while not self._initialized:
            await asyncio.sleep(0.1)
            wait_count += 1
            if wait_count > 50:  # 5 seconds max
                print("[ThreeStage] ERROR: Timeout waiting for initialization!")
                return

        # Allow a short grace period for init result
        if self._init_ok is None:
            for _ in range(10):
                await asyncio.sleep(0.1)
                if self._init_ok is not None:
                    break

        if self._init_ok is None:
            await self.probe_ready()
        if self._init_ok is False:
            print("[ThreeStage] Engine not ready; skipping add_card")
            return

        element_id = f"c{card_element.id}"
        print(f"[ThreeStage] Executing JS: window.engine.addCard('{element_id}')")

        # Diagnostic JS that logs back to Python
        diag_js = f'''
        (function() {{
            let result = {{}};
            result.engineExists = !!window.engine;
            result.elementExists = !!document.getElementById("{element_id}");
            if (result.elementExists) {{
                let el = document.getElementById("{element_id}");
                result.elementTag = el.tagName;
                result.elementParent = el.parentElement ? el.parentElement.id : 'no-parent';
            }}
            if (window.engine) {{
                try {{
                    window.engine.addCard("{element_id}");
                    result.addCardOK = true;
                }} catch(e) {{
                    result.addCardError = e.message;
                }}
            }}
            console.log("[3D-DIAG]", JSON.stringify(result));
            return JSON.stringify(result);
        }})()
        '''
        try:
            result = await ui.run_javascript(diag_js, timeout=10.0)
            print(f"[ThreeStage] JS diagnostic result: {result}")
        except Exception as e:
            print(f"[ThreeStage] JS diagnostic error: {e}")

    async def move_to_stack(self, card_element: ui.element):
        if not self._initialized: return
        await self.run_method_js(f'window.engine.moveToStack("c{card_element.id}")')

    async def discard(self, card_element: ui.element):
        if not self._initialized: return
        await self.run_method_js(f'window.engine.discard("c{card_element.id}")')
