from nicegui import ui, app
from typing import Optional, Dict
import asyncio

class ThreeStage(ui.element):
    def __init__(self):
        super().__init__('div')
        self.classes('w-full h-full relative overflow-hidden')
        self._initialized = False
        
        # 1. Setup Import Map for Three.js (Module resolution)
        # Using unpkg for standard modules. 
        # Note: CSS3DRenderer is in 'addons' in newer versions.
        import_map = """
        <script type="importmap">
          {
            "imports": {
              "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
              "three/addons/": "https://unpkg.com/three@0.160.0/examples/jsm/"
            }
          }
        </script>
        """
        ui.add_head_html(import_map)
        
        # 2. Load our Engine
        # type="module" allows using 'import' inside the file
        ui.add_head_html('<script type="module" src="/assets/js/card_engine.js"></script>')

        # 3. Initialize on Client
        self.on('mount', self._init_client_side)

    async def _init_client_side(self):
        # Create global instance bound to this container ID
        await self.run_method_js(f'window.engine = window.createCardEngine("{self.id}")')
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
