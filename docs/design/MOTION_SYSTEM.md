# Motion system

Depth tokens: environment 0, system 1, focused entity 2, detail 3, critical dialog 4.
Duration tokens: fast 140 ms, normal 260 ms, slow 600 ms. Focus uses a damped ease-out
curve; navigation and activation share these tokens. Activity has a slow orbital
phase, approval is restrained amber, uncertainty is asymmetric violet. State labels
remain authoritative even when animation is off.

The Canvas2D core projects a bounded spherical lattice. It measures frame duration,
reduces sampling on small screens/slow frames, pauses in hidden documents and when
offscreen, and renders a fixed frame under reduced motion or `?test=1`. No GPU/WebGL
dependency or particles are required. Missing Canvas2D leaves a labelled static core.

The execution stack uses its own standard scroll container. Depth, separation and
opacity are derived from container position; the rest of the application keeps normal
scroll behavior. Keyboard layer selection and a flat readable detail list cover the
same lineage. Previous layers remain identifiable, and breadcrumbs stay visible.

Organization tilt/zoom is bounded and resettable. Focus is explicit, not free-flight.
Relationships come from returned links/metadata, with absent edges identified as such.
Knowledge/message motion is only eligible for newly observed canonical events;
historical data renders without pretending an agent is acting now.

`prefers-reduced-motion`, explicit motion-off and deterministic test mode eliminate
continuous movement, depth travel and animated focus. Critical banners, errors and
record contents render immediately; motion never gates navigation.
