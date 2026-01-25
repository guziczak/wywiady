import * as THREE from 'three';
import { CSS3DRenderer, CSS3DObject } from 'three/addons/renderers/CSS3DRenderer.js';
import TWEEN from 'three/addons/libs/tween.module.js';

export class CardEngine {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.cards = new Map(); // id -> CSS3DObject
        this.isInitialized = false;
        
        this.init();
        this.animate();
    }

    init() {
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;

        // 1. Camera (Perspective) - Looking down at a desk
        this.camera = new THREE.PerspectiveCamera(40, width / height, 1, 5000);
        this.camera.position.set(0, 800, 1200); // High up, pulled back
        this.camera.lookAt(0, 0, 0);

        // 2. Scene
        this.scene = new THREE.Scene();

        // 3. Renderer
        this.renderer = new CSS3DRenderer();
        this.renderer.setSize(width, height);
        this.renderer.domElement.style.position = 'absolute';
        this.renderer.domElement.style.top = '0';
        this.renderer.domElement.style.left = '0';
        // pointer-events: auto on renderer so cards are clickable
        this.renderer.domElement.style.pointerEvents = 'auto';
        
        // Clear container and append renderer
        this.container.innerHTML = '';
        this.container.appendChild(this.renderer.domElement);

        // 4. Resize Handler
        window.addEventListener('resize', () => this.onWindowResize());
        
        this.isInitialized = true;
        console.log('[CardEngine] Initialized 3D Stage');
    }

    onWindowResize() {
        if (!this.container) return;
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;

        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    animate() {
        requestAnimationFrame(() => this.animate());
        TWEEN.update();
        this.renderer.render(this.scene, this.camera);
    }

    // === API ===

    addCard(elementId) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error(`[CardEngine] Element not found: ${elementId}`);
            return;
        }

        // IMPORTANT: Move element out of hidden staging container into renderer
        // CSS3DObject does NOT move elements, just applies transforms
        this.renderer.domElement.appendChild(element);
        console.log(`[CardEngine] Moved element ${elementId} to renderer, parent:`, element.parentElement);

        // Ensure element is visible and interactive
        element.style.display = 'block';
        element.style.pointerEvents = 'auto';
        element.style.opacity = '1';
        element.style.visibility = 'visible';

        const object = new CSS3DObject(element);
        console.log(`[CardEngine] Created CSS3DObject for ${elementId}`);
        
        // Initial Position: Above the camera, slightly random X
        const startX = (Math.random() - 0.5) * 200;
        object.position.set(startX, 1000, 500); 
        object.rotation.x = Math.PI / 2; // Flat facing down? No, let's rotate it randomly
        object.rotation.z = (Math.random() - 0.5) * 0.5;

        this.scene.add(object);
        this.cards.set(elementId, object);

        // Animate to Center (The "Deal")
        // Target: Center of desk (0, 0, 0)
        // Add slight random offset to prevent perfect overlap Z-fighting visual
        const targetX = (Math.random() - 0.5) * 50;
        const targetZ = (Math.random() - 0.5) * 50;
        const targetY = 0; // Desk level

        new TWEEN.Tween(object.position)
            .to({ x: targetX, y: targetY, z: targetZ }, 1000)
            .easing(TWEEN.Easing.Exponential.Out)
            .start();

        new TWEEN.Tween(object.rotation)
            .to({ x: -Math.PI / 2, y: 0, z: (Math.random() - 0.5) * 0.1 }, 1000) // Lay flat (-90deg on X)
            .easing(TWEEN.Easing.Cubic.Out)
            .start();
    }

    moveToStack(elementId) {
        const object = this.cards.get(elementId);
        if (!object) return;

        // Stack Position (e.g., Top Right)
        const stackX = 400;
        const stackZ = -200;
        
        new TWEEN.Tween(object.position)
            .to({ x: stackX, y: 0, z: stackZ }, 800)
            .easing(TWEEN.Easing.Back.In)
            .onComplete(() => {
                // Optional: Make it disappear or stay on stack
                // For now, let it stay
            })
            .start();

        // Rotate slightly as it flies to stack
        new TWEEN.Tween(object.rotation)
            .to({ z: Math.random() * 0.2 }, 800)
            .start();
    }

    discard(elementId) {
        const object = this.cards.get(elementId);
        if (!object) return;

        // Discard Position (e.g., Off screen Left)
        const discardX = -1000;
        
        new TWEEN.Tween(object.position)
            .to({ x: discardX, y: 0, z: 0 }, 600)
            .easing(TWEEN.Easing.Back.In)
            .onComplete(() => {
                this.scene.remove(object);
                this.cards.delete(elementId);
                // Element is still in DOM (inside CSS3DObject), but removed from scene. 
                // We might want to remove it from DOM too via Python callback, 
                // but for now visual removal is enough.
            })
            .start();
    }
}

// Global factory for NiceGUI to call
export function createCardEngine(containerId) {
    return new CardEngine(containerId);
}

window.createCardEngine = createCardEngine;
