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

**`device_types` observed values (live gateway, capitalised — NOT lowercase as documented):**

| Value | Meaning |
|---|---|
| `"Light"` | Controllable light node — create HA entity |
| `"Switch"` | Physical switch / remote / sensor node — input-only, no HA entity needed |

> The AsyncAPI spec shows lowercase type strings, but the real gateway sends capitalised values (`"Light"`, `"Switch"`). Case-insensitive matching required.

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

> **CRITICAL behaviour observed (live testing):** The status topic is **only published in response to explicit `powerGet`/`lightnessGet` commands**. It is **NOT published on physical state changes** (wall switch, remote toggle, dimmer). Physical changes arrive exclusively on `{gateway_topic}/rawMessage` as BLE Mesh Set Unack messages. Do not rely on this topic alone for push-based state tracking.

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

The gateway relays **every** BLE Mesh Access Message it receives to this topic. This is the **primary push channel** for physical state changes — wall switches, remotes, and dimmers publish Set Unack messages here immediately when the user acts, with no corresponding status-topic update.

```json
{
  "source": "0x7FFC",
  "destination": "0xC000",
  "opcode": "008203",
  "payload": "0100",
  "sequence_number": 42,
  "ttl": 5,
  "rssi": -65
}
```

| Field | Type | Description |
|---|---|---|
| `source` | string | BLE address of the originating device as a hex string (`"7FFC"` or `"0x7FFC"`) |
| `destination` | string | BLE destination address (hex) |
| `opcode` | string | 6-char uppercase hex string (see table below). May include `0x` prefix. |
| `payload` | string | Hex-encoded BLE Mesh message body |
| `sequence_number` | integer | BLE Mesh sequence counter — use to deduplicate mesh retransmits |
| `ttl` | integer | Time-to-live remaining hops |
| `rssi` | integer | Received signal strength (dBm) |

> **Source address:** The `source` field is always a **hex string**, not a decimal integer. However, `device_addr` in the discovery payload is a **decimal integer**. Convert `source` hex → int for coordinator lookup.

> **Retransmit deduplication:** BLE Mesh retransmits the same Set Unack message 2–3 times within ~100 ms. Use `(source, sequence_number)` as a dedup key to process each logical event only once.

> **Periodic keep-alive traffic:** The gateway publishes `rawMessage` approximately every 14 s for health/keep-alive traffic regardless of user activity. Filter by opcode — only process the opcodes listed below.

#### Opcode Reference (BLE Mesh → Gateway encoding)

The gateway encodes BLE Mesh opcodes as **6-char uppercase hex strings** with a `00` company-ID prefix followed by the 4-char SIG opcode. Example: SIG opcode `0x8203` → gateway string `"008203"`.

| Gateway opcode | BLE Mesh opcode | Model | Direction | Payload layout |
|---|---|---|---|---|
| `008201` | 0x8201 | Generic OnOff | Get (HA → device) | none |
| `008202` | 0x8202 | Generic OnOff | Set Ack (HA → device) | `[OnOff u8][TID u8][TransTime?][Delay?]` |
| **`008203`** | **0x8203** | **Generic OnOff** | **Set Unack (device → gw, physical change)** | `[OnOff u8][TID u8][TransTime?][Delay?]` |
| `008204` | 0x8204 | Generic OnOff | Status (device → gw, response to Get) | `[PresentOnOff u8][TargetOnOff?][RemTime?]` |
| `00824B` | 0x824B | Light Lightness | Get (HA → device) | none |
| `00824C` | 0x824C | Light Lightness | Set Ack (HA → device) | `[Lightness u16LE][TID u8]…` |
| **`00824D`** | **0x824D** | **Light Lightness** | **Set Unack (device → gw, physical change)** | `[Lightness u16LE][TID u8]…` |
| `00824E` | 0x824E | Light Lightness | Status (device → gw, response to Get) | `[PresentLightness u16LE][TargetLightness?]…` |
| `008262` | 0x8262 | Light CTL | Set Unack (physical / command) | `[Lightness u16LE][Temp u16LE Kelvin][DeltaUV i16LE][TID u8]…` |
| `008263` | 0x8263 | Light CTL | Status (response to Get) | `[Lightness u16LE][Temp u16LE Kelvin]…` |
| `008278` | 0x8278 | Light HSL | Set Unack (physical / command) | `[Lightness u16LE][Hue u16LE][Sat u16LE][TID u8]…` |
| `008279` | 0x8279 | Light HSL | Status (response to Get) | `[Lightness u16LE][Hue u16LE][Sat u16LE]…` |

**Opcodes verified by live observation:**
- `008203` — seen from device addr `0x7FFC` ("Hal beneden") on physical wall-switch toggle
- `00824D` — seen from same device during physical dimming

**Payload decoding rules:**

| Model | Fields | Notes |
|---|---|---|
| Generic OnOff | `payload[0]` = OnOff (0/1) | TID at byte 1, ignored |
| Light Lightness | `payload[0:2]` = Lightness uint16 LE (0–65535) | TID at byte 2, ignored |
| Light CTL | `payload[0:2]` = Lightness uint16 LE; `payload[2:4]` = Temperature uint16 LE (Kelvin, direct value) | DeltaUV at bytes 4–5 (usually 0) |
| Light HSL | `payload[0:2]` = Lightness uint16 LE; `payload[2:4]` = Hue uint16 LE (0–65535 → 0–360°); `payload[4:6]` = Saturation uint16 LE (0–65535 → 0.0–1.0) | |

**Scale conversions from rawMessage payload values:**

| Parameter | Raw (payload) | HA internal scale | Notes |
|---|---|---|---|
| OnOff | 0/1 byte | `bool` | |
| Lightness | 0–65535 uint16 LE | 0–65535 mesh scale | Convert to HA 0–255 via `value_to_brightness(BRIGHTNESS_SCALE_MESH, v)` |
| Temperature (CTL) | uint16 LE **Kelvin** (direct, NOT mesh-scaled) | 0–65535 via `(K − 2000) / 4500 × 65535` | Clamp to 2000–6500 K before converting |
| Hue (HSL) | 0–65535 uint16 LE | degrees: `v / 65535 × 360` | |
| Saturation (HSL) | 0–65535 uint16 LE | ratio: `v / 65535` | |

> **Temperature note:** CTL payload bytes 2–3 carry the colour temperature directly in **Kelvin** as a uint16 LE. This differs from lightness/hue/saturation which use the full 0–65535 mesh range. The value must be clamped to the integration's supported range (2000–6500 K) before converting to the internal 0–65535 scale.

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

## Field Name Reference (Discovery Payload)

The discovery payload uses verbose field names. Confirmed correct names (bugs in early integration code used wrong names — all fixed):

| Field | Type | Notes |
|---|---|---|
| `device_name` | string | Human-readable name. Used verbatim in status/command topic paths (spaces are literal, not URL-encoded). |
| `device_addr` | **integer** | BLE mesh address as a **decimal integer** (e.g. `32764`). Use as `int`. |
| `device_types` | `string[]` | Capability list. Gateway sends **capitalised** values (`"Light"`, `"Switch"`), not lowercase as documented. Use case-insensitive matching. |
| `location` | string | Room/area name. Used to auto-assign HA areas. |

> **Topic paths use literal device names:** MQTT topic paths such as `hafele/lights/Hal beneden/status` contain the literal `device_name` string including spaces. Do **not** URL-encode device names in topic strings.

## Integration Implementation Notes

Accumulated findings from live testing against a real Häfele Connect Mesh gateway:

1. **Status topic is response-only.** `hafele/lights/{name}/status` is published only when the gateway responds to a `powerGet`/`lightnessGet` command. Physical toggles do NOT trigger it.

2. **rawMessage is the true push channel.** Subscribe to `{prefix}/rawMessage` and decode BLE Mesh opcodes (see above) for real-time physical state changes.

3. **Deduplicate by (source, sequence_number).** BLE Mesh retransmits the same event 2–3 times. A simple set of `(int(source_hex, 16), sequence_number)` tuples prevents duplicate state updates.

4. **device_types values are capitalised.** Real gateway sends `"Light"` and `"Switch"`, not `"light"` and `"switch"`.

5. **Bare `on`/`off` power payloads are rejected.** The gateway JSON-parses all command payloads. Send `true`/`false` (JSON booleans) or `"on"`/`"off"` (quoted JSON strings). Bare `on` is invalid JSON and silently ignored.

6. **Status topic field is `onoff` (lowercase).** Device status uses `{"onoff": 1}` (lowercase key, integer value), not `{"onOff": "on"}` (which is the group-status format).

7. **URL-encoding device names breaks subscriptions.** Topic subscriptions must use literal device names. `hafele/lights/Hal%20beneden/status` will never receive messages; `hafele/lights/Hal beneden/status` is correct.

8. **Keep-alive rawMessage traffic.** The gateway sends periodic `rawMessage` broadcasts (~every 14 s) unrelated to device state. Filter by opcode to avoid spurious state updates.
