# Root motion and IK

Two steps that run after blending and before skinning. **Root motion** takes the movement authored in the clips and gives it to the character controller, so feet do not slide. **Inverse kinematics** adjusts the pose to the world the clip was not made for: uneven ground, a door handle at a different height, a target to look at.

## Root motion

An animator who makes a character walk forward moves the whole skeleton forward through the clip, by the root bone. In the game, the character controller moves the character, so the root's movement must be taken out of the pose and handed to it.

```text
extract_root_motion(clip, t0, t1):
    if t1 >= t0:
        delta = root_at(t1) relative to root_at(t0)
    else:                                              // wrapped around the end of a loop
        delta = (root_at(end) relative to root_at(t0)) then (root_at(t1) relative to root_at(0))
    remove the root's translation and yaw from the pose (keep its height and pitch if wanted)
    return delta                                       // translation and yaw, in the character's space
```

- Express the delta in the character's **local space** (forward is forward), and rotate it into world space with the character's facing when applying it.
- With blending, **blend the deltas** with the same weights as the poses. A walk and a run blended 50/50 then move at a speed between the two, and the feet match.
- Give the delta to the **character controller** as its desired movement for the frame, so it still collides, slides along walls, and falls off ledges. Applying it straight to the position walks through walls.
- Decide per state whether movement comes from root motion (attacks, climbs, cinematic moves, where exact placement matters) or from gameplay code (locomotion, where responsiveness matters more than foot accuracy). Most games mix the two.

The [root motion](../../unity/animation/root-motion.md) page covers the Unity version.

## Two-bone IK

Most game IK is a chain of two bones: upper arm and forearm reaching for a target, or thigh and shin placing a foot. It has an exact solution from the law of cosines:

```text
two_bone_ik(root, mid, end, target, pole):              // model-space positions
    a = length(mid - root)                               // upper bone length
    b = length(end - mid)                                // lower bone length
    c = clamp(length(target - root), epsilon, a + b - epsilon)    // cannot reach farther than the chain

    // Bend the middle joint so the chain's span becomes c.
    current_mid_angle = angle between (root - mid) and (end - mid)
    wanted_mid_angle  = acos(clamp((a*a + b*b - c*c) / (2*a*b), -1, 1))
    rotate mid around the bend axis by (wanted_mid_angle - current_mid_angle)

    // Point the chain at the target.
    rotate root so that (end - root) points along (target - root)

    // Twist the chain around the root-to-target line so the middle joint points towards the pole.
    rotate root around normalize(target - root) to bring mid towards pole
```

- The **bend axis** is perpendicular to the plane of the three joints, taken from the current pose, so the knee keeps bending the way it already does. Recompute it from the pole when the chain is straight, where the plane is undefined.
- The **pole** (or hint) is a point the elbow or knee should point towards: in front of the knee, behind the elbow. Without it, the chain can flip to bend the wrong way.
- Clamp the reach a little short of fully straight. A chain stretched exactly straight snaps when the target moves slightly closer, because the bend direction is undefined there.
- Apply IK in **model space** after blending, then convert the changed bones back to local space if later steps need local poses.

Longer chains (spines, tails, tentacles) use iterative solvers: **FABRIK** moves joints back and forth along the chain to match the target, and **CCD** (cyclic coordinate descent) rotates each joint in turn towards the target. Both converge in a few iterations, but need joint limits to look natural.

## Foot planting

Animation is authored on flat ground. On slopes and stairs, one foot floats and the other sinks. Foot IK fixes it:

```text
foot_ik(character):
    for foot in left, right:
        ray from above the animated foot position straight down
        if hit: foot.target = hit.point + foot_height_above_sole; foot.normal = hit.normal

    // Lower the hips so the lower foot can reach the ground.
    offset = min(left.target.y - left.animated.y, right.target.y - right.animated.y, 0)
    pelvis.y += smooth(offset)

    for foot in left, right:
        two_bone_ik(thigh, shin, foot, foot.target, knee_pole)
        rotate the foot to align its sole with foot.normal (limited to a maximum angle)
```

- **Lower the pelvis** by the larger drop, never raise it. Raising it would make the legs over-extend; lowering lets both feet reach.
- **Smooth** the pelvis offset and foot targets over time, or the character pops every time a ray hits a different step.
- **Blend IK by foot contact**: apply full IK when the foot is planted, none when it is swinging. A curve in the clip (or a foot-down marker, as used for [synchronising cycles](blending.md#synchronising-cycles)) gives the weight.
- Turn foot IK **off** while airborne, and fade it in on landing.
- Cast **spheres** rather than rays for the ground check, so feet do not catch on tiny gaps between steps.

## Look-at and aim

Turning the head (or a weapon) towards a target is a rotation spread over several bones:

```text
look_at(target):
    direction to target in the character's space
    clamp the yaw and pitch to the head's limits (e.g. ±70° yaw, ±40° pitch)
    split the rotation across spine 0.2, chest 0.3, neck 0.2, head 0.3
    smooth towards the clamped rotation with a maximum turn rate
```

Spreading the rotation over several bones looks natural, where turning only the head looks like an owl. When the target moves outside the limits, return smoothly to neutral rather than snapping. The Unity versions are on the [IK](../../unity/animation/ik.md) page.
