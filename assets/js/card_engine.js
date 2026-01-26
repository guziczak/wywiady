import * as THREE from 'three';
import { CSS3DRenderer, CSS3DObject } from 'three/addons/renderers/CSS3DRenderer.js';
import TWEEN from 'three/addons/libs/tween.module.js';

export class CardEngine {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.cards = new Map(); // id -> CSS3DObject
        this.isInitialized = false;

        this.prefersReducedMotion = window.matchMedia
            && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        this.focusLevel = 0; // 0 = normal, 1 = focus (reduced motion)
        this._lastTime = performance.now();
        this.baseCamera = { x: 0, y: 800, z: 1200 };
        this.parallax = { x: 0, z: 0 };
        this.parallaxTarget = { x: 0, z: 0 };
        this.breathing = {
            phase: Math.random() * Math.PI * 2,
            amp: 10,
            speed: 0.0006,
        };
        this.hoverState = {
            activeId: null,
            leaveTimer: null,
            switchLockUntil: 0,
            lockMs: 180,
            releaseMs: 140,
        };
        
        this.init();
        this.animate();
    }

    init() {
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;

        // 1. Camera (Perspective) - Looking down at a desk
        this.camera = new THREE.PerspectiveCamera(40, width / height, 1, 5000);
        this.camera.position.set(this.baseCamera.x, this.baseCamera.y, this.baseCamera.z); // High up, pulled back
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

        // 4. Motion input
        this._attachMotionHandlers();

        // 5. Resize Handler
        window.addEventListener('resize', () => this.onWindowResize());
        this.container.addEventListener('pointerleave', () => {
            if (this.hoverState.activeId) {
                this._dropCard(this.hoverState.activeId, true);
                this.hoverState.activeId = null;
            }
        }, { passive: true });
        
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
        this._updateCameraMotion(performance.now());
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
        // Use a gentle spiral stack for more natural piling
        const index = this.cards.size;
        const { targetX, targetY, targetZ, targetRot } = this._computeStackTransform(index);

        object.userData.home = {
            x: targetX,
            y: targetY,
            z: targetZ,
            rx: targetRot.x,
            ry: targetRot.y,
            rz: targetRot.z,
        };
        object.userData.hovered = false;

        new TWEEN.Tween(object.position)
            .to({ x: targetX, y: targetY, z: targetZ }, 1000)
            .easing(TWEEN.Easing.Exponential.Out)
            .start();

        new TWEEN.Tween(object.rotation)
            .to(targetRot, 1000) // Lay flat (-90deg on X)
            .easing(TWEEN.Easing.Cubic.Out)
            .start();

        this._attachCardInteractions(element, elementId);
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

    setCardVisible(elementId, visible = true) {
        const object = this.cards.get(elementId);
        if (!object) return;
        if (!visible && this.hoverState.activeId === elementId) {
            this._dropCard(elementId, true);
            this.hoverState.activeId = null;
        }
        object.visible = !!visible;
        if (object.element) {
            object.element.style.display = visible ? 'block' : 'none';
            object.element.style.opacity = visible ? '1' : '0';
        }
    }

    restackVisible(elementIds = []) {
        if (!Array.isArray(elementIds)) return;
        const ids = elementIds.filter((id) => this.cards.has(id));
        ids.forEach((elementId, idx) => {
            const object = this.cards.get(elementId);
            if (!object) return;
            const { targetX, targetY, targetZ, targetRot } = this._computeStackTransform(idx + 1);
            object.userData.home = {
                x: targetX,
                y: targetY,
                z: targetZ,
                rx: targetRot.x,
                ry: targetRot.y,
                rz: targetRot.z,
            };
            if (object.userData.hovered) {
                this._dropCard(elementId, true);
            }
            new TWEEN.Tween(object.position)
                .to({ x: targetX, y: targetY, z: targetZ }, 520)
                .easing(TWEEN.Easing.Cubic.Out)
                .start();
            new TWEEN.Tween(object.rotation)
                .to(targetRot, 520)
                .easing(TWEEN.Easing.Cubic.Out)
                .start();
        });
    }

    setFocus(level = 0) {
        this.focusLevel = Math.max(0, Math.min(1, level));
    }

    setMotionEnabled(enabled = true) {
        this.prefersReducedMotion = !enabled;
    }

    _attachCardInteractions(element, elementId) {
        element.addEventListener('pointerenter', (event) => {
            this._onCardEnter(elementId, event);
        }, { passive: true });

        element.addEventListener('pointerleave', (event) => {
            this._onCardLeave(elementId, event);
        }, { passive: true });
    }

    _onCardEnter(elementId, event) {
        const now = performance.now();
        if (this.hoverState.leaveTimer) {
            clearTimeout(this.hoverState.leaveTimer);
            this.hoverState.leaveTimer = null;
        }
        if (this.hoverState.activeId && this.hoverState.activeId !== elementId) {
            if (now < this.hoverState.switchLockUntil) {
                return;
            }
            this._dropCard(this.hoverState.activeId, true);
        }
        this.hoverState.activeId = elementId;
        this.hoverState.switchLockUntil = now + this.hoverState.lockMs;
        this._liftCard(elementId);
    }

    _onCardLeave(elementId, event) {
        if (this.hoverState.activeId !== elementId) return;
        const object = this.cards.get(elementId);
        if (event && object && object.element) {
            const rect = object.element.getBoundingClientRect();
            const margin = 24;
            if (
                event.clientX >= rect.left - margin &&
                event.clientX <= rect.right + margin &&
                event.clientY >= rect.top - margin &&
                event.clientY <= rect.bottom + margin
            ) {
                return;
            }
        }
        if (this.hoverState.leaveTimer) {
            clearTimeout(this.hoverState.leaveTimer);
        }
        this.hoverState.leaveTimer = setTimeout(() => {
            if (this.hoverState.activeId === elementId) {
                this._dropCard(elementId, true);
                this.hoverState.activeId = null;
            }
        }, this.hoverState.releaseMs);
    }

    _liftCard(elementId) {
        const object = this.cards.get(elementId);
        if (!object || object.userData.hovered) return;
        const home = object.userData.home;
        if (!home) return;
        object.userData.hovered = true;

        const focusPull = 0.55;
        const liftPos = {
            x: home.x * (1 - focusPull),
            y: home.y + 32,
            z: home.z * (1 - focusPull) + 180,
        };
        const liftRot = { x: -Math.PI / 2, y: 0, z: 0 };

        object.userData.hoverTween?.stop?.();
        const posTween = new TWEEN.Tween(object.position)
            .to(liftPos, 240)
            .easing(TWEEN.Easing.Cubic.Out);
        const rotTween = new TWEEN.Tween(object.rotation)
            .to(liftRot, 240)
            .easing(TWEEN.Easing.Cubic.Out);
        posTween.start();
        rotTween.start();
        object.userData.hoverTween = posTween;
    }

    _dropCard(elementId, force = false) {
        const object = this.cards.get(elementId);
        if (!object) return;
        if (!force && !object.userData.hovered) return;
        const home = object.userData.home;
        if (!home) return;
        object.userData.hovered = false;

        object.userData.hoverTween?.stop?.();
        const posTween = new TWEEN.Tween(object.position)
            .to({ x: home.x, y: home.y, z: home.z }, 260)
            .easing(TWEEN.Easing.Cubic.Out);
        const rotTween = new TWEEN.Tween(object.rotation)
            .to({ x: home.rx, y: home.ry, z: home.rz }, 260)
            .easing(TWEEN.Easing.Cubic.Out);
        posTween.start();
        rotTween.start();
        object.userData.hoverTween = posTween;
    }

    _computeStackTransform(index) {
        const angle = index * 0.55;
        const radius = 20 + Math.min(index, 16) * 2.2;
        const jitter = (this._pseudoRandom(index * 3.1) - 0.5) * 10;
        const targetX = Math.cos(angle) * radius + jitter;
        const targetZ = Math.sin(angle) * radius + jitter;
        const targetY = Math.min(index * 0.35, 6);
        const targetRot = {
            x: -Math.PI / 2,
            y: (this._pseudoRandom(index * 5.7) - 0.5) * 0.08,
            z: (this._pseudoRandom(index * 8.3) - 0.5) * 0.12,
        };
        return { targetX, targetY, targetZ, targetRot };
    }

    _pseudoRandom(seed) {
        const x = Math.sin(seed) * 10000;
        return x - Math.floor(x);
    }

    _attachMotionHandlers() {
        if (!this.container) return;

        const updateTarget = (clientX, clientY) => {
            if (this.prefersReducedMotion) return;
            const rect = this.container.getBoundingClientRect();
            if (!rect.width || !rect.height) return;
            const x = (clientX - rect.left) / rect.width;
            const y = (clientY - rect.top) / rect.height;
            this.parallaxTarget.x = (x - 0.5) * 2;
            this.parallaxTarget.z = (y - 0.5) * 2;
        };

        this.container.addEventListener('pointermove', (event) => {
            updateTarget(event.clientX, event.clientY);
        }, { passive: true });

        this.container.addEventListener('pointerleave', () => {
            this.parallaxTarget.x = 0;
            this.parallaxTarget.z = 0;
        }, { passive: true });

        this.container.addEventListener('touchmove', (event) => {
            if (!event.touches || !event.touches[0]) return;
            updateTarget(event.touches[0].clientX, event.touches[0].clientY);
        }, { passive: true });
    }

    _updateCameraMotion(now) {
        if (this.prefersReducedMotion) return;

        const focusFactor = 1 - (this.focusLevel * 0.65);
        const targetX = this.parallaxTarget.x * 40 * focusFactor;
        const targetZ = this.parallaxTarget.z * 30 * focusFactor;

        this.parallax.x += (targetX - this.parallax.x) * 0.05;
        this.parallax.z += (targetZ - this.parallax.z) * 0.05;

        const breath = Math.sin(now * this.breathing.speed + this.breathing.phase)
            * this.breathing.amp * (0.4 + (1 - this.focusLevel) * 0.6);

        this.camera.position.set(
            this.baseCamera.x + this.parallax.x,
            this.baseCamera.y + breath,
            this.baseCamera.z + this.parallax.z
        );
        this.camera.lookAt(0, 0, 0);
    }
}

// Global factory for NiceGUI to call
export function createCardEngine(containerId) {
    return new CardEngine(containerId);
}

window.createCardEngine = createCardEngine;
