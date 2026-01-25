from nicegui import ui, app
from typing import Optional, Dict
import asyncio

class ThreeStage(ui.element):
    def __init__(self):
        super().__init__('div')
        self.classes('w-full h-full relative overflow-hidden')
        self._initialized = False
        
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

        # 3. Initialize on Client
        self.on('mount', self._init_client_side)

    async def _init_client_side(self):
        # Dynamically import the module to guarantee it's loaded
        js_init = f'''
        import('/assets/js/card_engine.js').then(module => {{
            window.engine = module.createCardEngine("{self.id}");
        }}).catch(err => console.error("Failed to load 3D engine:", err));
        '''
        await self.run_method_js(js_init)
        self._initialized = True

    async def run_method_js(self, code: str):
        """Helper to run JS safely."""
        await ui.run_javascript(code, respond=False)

    async def add_card(self, card_element: ui.element):
        """
        Takes a NiceGUI element (the card), ensures it's mounted, 
        and passes its ID to the 3D engine.
        """
        # Element must be in the DOM. 
        # We assume the card is created as a child of a hidden container elsewhere, 
        # or we move it here. 
        # For CSS3D, the element is moved by the renderer, so its initial parent doesn't matter much
        # as long as it exists.
        
        # Wait for init
        while not self._initialized:
            await asyncio.sleep(0.1)

        # Execute JS
        await self.run_method_js(f'window.engine.addCard("c{card_element.id}")')

    async def move_to_stack(self, card_element: ui.element):
        if not self._initialized: return
        await self.run_method_js(f'window.engine.moveToStack("c{card_element.id}")')

    async def discard(self, card_element: ui.element):
        if not self._initialized: return
        await self.run_method_js(f'window.engine.discard("c{card_element.id}")')
