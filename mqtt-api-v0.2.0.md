# Häfele Connect MQTT API v0.2.0

> Source: https://help.connect-mesh.io/mqtt/index.html
> AsyncAPI version: 3.0.0 · Content type: `application/json`

The Häfele Connect MQTT API lets you control Connect Devices (lights) through a Connect Gateway over MQTT.

---

## Topic Prefix (`gateway_topic`)

All topics are prefixed with a configurable **`gateway_topic`** (default: `hafele`). Each gateway has its own root topic. Replace `{gateway_topic}` accordingly in all topics below.

Device and group names are **URL-escaped** in topic paths.

---

## Discovery (RECEIVE)

These topics are published by the gateway, typically on connection or retained.

### `{gateway_topic}/lights`

Published once when the gateway comes online. Lists all known light devices.

**Payload:** `Array<Object>`

```json
[
  {
    "device_name": "Kitchen Light",
    "location": "Kitchen",
    "device_addr": 12345,
    "device_types": ["light"]
  }
]
```

| Field | Type | Description |
|---|---|---|
| `device_name` | string | Human-readable name |
| `location` | string | Room/location string |
| `device_addr` | integer | BLE mesh address |
| `device_types` | `string[]` | Capabilities: `"light"`, `"multiwhite"`, `"rgb"` |

> **Note for this integration:** The current code reads `item["name"]` and `item["addr"]` but the API uses `device_name` and `device_addr`. See bug in `__init__.py` `_on_discovery`.

---

### `{gateway_topic}/groups`

Lists all configured device groups.

**Payload:** `Array<Object>`

```json
[
  {
    "group_name": "Living Room",
    "devices": [12345, 12346],
    "group_main_addr": 49152
  }
]
```

| Field | Type | Description |
|---|---|---|
| `group_name` | string | Group name |
| `devices` | `integer[]` | BLE mesh addresses of member devices |
| `group_main_addr` | integer | The group's primary BLE address |

---

### `{gateway_topic}/scenes`

Lists all configured scenes.

**Payload:** `Array<Object>`

```json
[
  {
    "scene": "Dinner",
    "groups": [49152]
  }
]
```

| Field | Type | Description |
|---|---|---|
| `scene` | string | URL-escaped scene name |
| `groups` | `integer[]` | Group main addresses this scene applies to |

---

## Status Updates (RECEIVE)

### `{gateway_topic}/lights/{device_name}/status`

Real-time state updates for a specific device. Payload is one of the status objects below.

> **Field name note (confirmed from cross-reference):** Device status uses `"onoff"` (lowercase) with **numeric** values `1` (on) / `0` (off), not the camelCase `"onOff"` shown in the AsyncAPI spec. Group status uses `"onOff"` (camelCase) with string values `"on"`/`"off"`. Our `_normalize` checks for `"onoff"` which is correct for device status.

### `{gateway_topic}/groups/{group_name}/status`

Real-time state updates for a group. Payload is one of:

**OnOff status (device):**
```json
{ "onoff": 1, "transition_time": 5 }
```

**OnOff status (group):**
```json
{ "onOff": "on", "transition_time": 5 }
```

**Lightness status:**
```json
{ "lightness": 0.8, "transition_time": 10 }
```

**Color temperature status:**
```json
{ "temperature": 4000, "transition_time": 0 }
```

**Hue status:**
```json
{ "hue": 180 }
```

**Saturation status:**
```json
{ "saturation": 0.6 }
```

**HSL status (combined):**
```json
{ "hue": 180, "saturation": 0.6, "lightness": 0.8 }
```

**CTL status (combined color temp + lightness):**
```json
{ "lightness": 0.8, "temperature": 4000 }
```

---

### `{gateway_topic}/groups/{group_name}/received/recallScene`

Notifies that a group received a scene recall command. Payload is either:
- A string (escaped scene name): `"Dinner"`
- An object: `{ "scene": "Dinner" }`

---

## Control Commands (SEND)

Send these topics to the gateway to control devices or groups. Group commands apply to all devices in the group; device commands target a specific device.

### Power

| Topic | Payload |
|---|---|
| `{gateway_topic}/groups/{group_name}/power` | `true` / `false` / `"on"` / `"off"` |
| `{gateway_topic}/lights/{light_name}/power` | same |
| `{gateway_topic}/groups/{group_name}/powerGet` | `null` (empty) |
| `{gateway_topic}/lights/{light_name}/powerGet` | `null` (empty) |

```json
true
```
```json
"off"
```

> **Payload encoding note:** Payloads are JSON-parsed by the gateway. Send `true`/`false` (JSON booleans) or `"on"`/`"off"` (JSON strings with quotes). Bare unquoted strings like `on` are **not valid JSON** and will be silently rejected. Our integration sends `true`/`false` via `json.dumps(bool)`.

---

### Lightness (Brightness)

Value range: `0.0` – `1.0`

| Topic | Payload |
|---|---|
| `{gateway_topic}/groups/{group_name}/lightness` | number or `{ "lightness": 0.8, "transition_time": 10 }` |
| `{gateway_topic}/lights/{device_name}/lightness` | same |
| `{gateway_topic}/groups/{group_name}/lightnessGet` | `null` |
| `{gateway_topic}/lights/{light_name}/lightnessGet` | `null` |

```json
0.75
```
```json
{ "lightness": 0.75, "transition_time": 20 }
```

---

### Color Temperature

Value range: `800` – `20000` Kelvin

| Topic | Payload |
|---|---|
| `{gateway_topic}/groups/{group_name}/temperature` | integer or `{ "temperature": 4000, "transition_time": 10 }` |
| `{gateway_topic}/lights/{device_name}/temperature` | same |

```json
3000
```
```json
{ "temperature": 3000, "transition_time": 5 }
```

---

### Hue

Value range: `0` – `360` degrees

| Topic | Payload |
|---|---|
| `{gateway_topic}/groups/{group_name}/hue` | integer or `{ "hue": 120, "transition_time": 5 }` |
| `{gateway_topic}/lights/{device_name}/hue` | same |

---

### Saturation

Value range: `0.0` – `1.0`

| Topic | Payload |
|---|---|
| `{gateway_topic}/groups/{group_name}/saturation` | number or `{ "saturation": 0.8, "transition_time": 5 }` |
| `{gateway_topic}/lights/{device_name}/saturation` | same |

---

### HSL (combined Hue + Saturation + Lightness)

| Topic | Payload |
|---|---|
| `{gateway_topic}/groups/{group_name}/hsl` | `{ "hue": 120, "saturation": 0.8, "lightness": 0.7 }` |
| `{gateway_topic}/lights/{device_name}/hsl` | same |
| `{gateway_topic}/groups/{group_name}/hslGet` | `null` |
| `{gateway_topic}/lights/{light_name}/hslGet` | `null` |

```json
{ "hue": 120, "saturation": 0.8, "lightness": 0.7, "transition_time": 10 }
```

---

### CTL (combined Color Temperature + Lightness)

| Topic | Payload |
|---|---|
| `{gateway_topic}/groups/{group_name}/ctl` | `{ "lightness": 0.8, "temperature": 4000 }` |
| `{gateway_topic}/lights/{device_name}/ctl` | same |
| `{gateway_topic}/groups/{group_name}/ctlGet` | `null` |
| `{gateway_topic}/lights/{light_name}/ctlGet` | `null` |

```json
{ "lightness": 0.8, "temperature": 4000, "transition_time": 10 }
```

---

### Scenes

**Recall a scene globally:**
```
SEND {gateway_topic}/scenes/recallScene
SEND {gateway_topic}/scenes/recall_scene   (legacy alias)
```
Payload: string (escaped scene name)
```json
"Dinner"
```

**Recall a scene for a group:**
```
SEND {gateway_topic}/groups/{group_name}/recallScene
SEND {gateway_topic}/groups/{group_name}/recall_scene   (legacy alias)
```

**Recall a scene for a specific device:**
```
SEND {gateway_topic}/lights/{device_name}/recallScene
SEND {gateway_topic}/lights/{device_name}/recall_scene   (legacy alias)
```

---

## Network Configuration (SEND)

### `{gateway_topic}/setNetworkConfiguration`

Sends the full device/group/scene configuration to the gateway. Rarely needed in normal operation.

**Payload:**
```json
{
  "devices": [ /* array of lightInfo objects */ ],
  "groups":  [ /* array of groupInfo objects */ ],
  "scenes":  [ /* array of sceneInfo objects */ ]
}
```

---

## Raw MQTT Access

For advanced / low-level use.

### `{gateway_topic}/rawMessage/send` (SEND)

Send a raw BLE Mesh Access Message:

```json
{
  "destination": 12345,
  "opcode": 33024,
  "payload": "0100"
}
```

| Field | Type | Description |
|---|---|---|
| `destination` | number | Target BLE address |
| `opcode` | number | BLE Mesh opcode (decimal) |
| `payload` | string | Hex-encoded payload |

### `{gateway_topic}/rawMessage` (RECEIVE)

Receive raw BLE Mesh Access Messages from devices:

```json
{
  "source": "0x3039",
  "destination": "0xC000",
  "opcode": "0x8101",
  "payload": "0000",
  "sequence_number": 42,
  "ttl": 5,
  "rssi": -65
}
```

---

## `transition_time` Parameter

Optional on all control commands. Specifies transition duration in **deciseconds (0.1 s steps)**. Value range: `0` – `372000`.

Due to BLE Mesh resolution limits, values are rounded down to the nearest supported increment:

| Range | Resolution |
|---|---|
| 0 – 6.2 s | 0.1 s steps |
| 0 – 62 s | 1 s steps |
| 0 – 10.5 min | 10 s steps |
| up to 10.5 hours | 10 min steps |

---

## Key Field Name Corrections (vs. Current Integration Code)

The current `_on_discovery` handler in `__init__.py` uses incorrect field names:

| Code uses | API actually sends |
|---|---|
| `item["name"]` | `item["device_name"]` |
| `item["addr"]` | `item["device_addr"]` |
| `item.get("types", ...)` | `item["device_types"]` |

This causes all 11 discovered devices to be skipped with `KeyError: 'name'`.
