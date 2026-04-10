# Ideas / Future Work

## Support for multiple pods per level

The game currently only supports a single pod (type $05) per level. The tractor beam activation check at `thrust.6502:4572` reads `level_obj_flags` without an `,X` index, hardcoding it to object index 0. All pod physics and rendering use single-instance variables (`pod_xpos`, `pod_ypos`, `pod_attached_flag`, etc.), not arrays.

**Current constraint:** the pod must be the first object (index 0) in each level's object list. The level editor export enforces this by sorting objects so that type $05 always comes first.

**To support multiple pods would require:**
- Changing `update_pod_tractor_beam` (line 4572) to use indexed access (`level_obj_flags,X`) with the current pod's object index stored in a variable
- Adding logic to select the nearest visible pod when the tractor beam is activated
- Either converting pod state variables to arrays (to track multiple attached/detached pods) or limiting the player to interacting with one pod at a time while allowing multiple to exist in the level
