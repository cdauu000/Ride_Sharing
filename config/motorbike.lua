-- OSRM v5.27.1 profile. Speeds require local calibration (V-03).
api_version = 4
local car = dofile('/opt/car.lua')
local Sequence = require('lib/sequence')

local function setup_motorbike()
  local profile = car.setup()
  profile.access_tags_hierarchy = Sequence {'motorcycle', 'motor_vehicle', 'vehicle', 'access'}
  profile.restrictions = Sequence {'motorcycle', 'motor_vehicle', 'vehicle'}
  profile.vehicle_height = 1.5
  profile.vehicle_width = 0.8
  profile.vehicle_length = 2.0
  profile.vehicle_weight = 250
  local urban = {'primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','residential','service'}
  for _, highway in ipairs(urban) do
    profile.speeds.highway[highway] = profile.speeds.highway[highway] * 1.18
  end
  return profile
end

local function process_motorbike_way(profile, way, result, relations)
  local highway = way:get_value_by_key('highway')
  local motorroad = way:get_value_by_key('motorroad')
  if highway == 'motorway' or highway == 'motorway_link' or motorroad == 'yes' then
    return
  end
  return car.process_way(profile, way, result, relations)
end

return {setup=setup_motorbike, process_node=car.process_node,
        process_way=process_motorbike_way, process_turn=car.process_turn}
