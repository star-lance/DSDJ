# Mixxx Configuration Plan

> **For Claude:** Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Write the Mixxx 2.4 MIDI mapping XML and the required JS stub so Mixxx recognises all DualSense DJ MIDI messages.

**Files:** `src/mixxx/midi_mapping.xml`, `src/mixxx/midi_mapping.js`
**Install target:** `~/.mixxx/controllers/`
**Dependencies:** none — can be written independently of the Python code.

---

## Task 1: Write `midi_mapping.js` stub

This file must exist or Mixxx will refuse to load the mapping.

Write `src/mixxx/midi_mapping.js`:

```javascript
// DualSense DJ — Mixxx MIDI Scripting Stub
// Extend this file to add scripted behaviors (pitch nudge scaling, etc.)
var DualSenseDJ = {};

DualSenseDJ.init = function(id, debugging) {
    // Called when the mapping is loaded
};

DualSenseDJ.shutdown = function(id) {
    // Called when the mapping is unloaded
};
```

---

## Task 2: Write `midi_mapping.xml`

Write `src/mixxx/midi_mapping.xml` with the complete mapping for Mixxx 2.4.

Key notes for Mixxx 2.4:
- Deck A = `[Channel1]`, Deck B = `[Channel2]`
- EQ rack: `[EqualizerRack1_[Channel1]_Effect1]` (parameter1=low, parameter2=mid, parameter3=high)
- Filter (QuickEffect): `[QuickEffectRack1_[Channel1]]`, key=`super1`
- Library: `[Library]`, key=`MoveVertical`
- Effects: `[EffectRack1_EffectUnit1]` key=`mix`, `[EffectRack1_EffectUnit1_Effect1]` key=`parameter1`

```xml
<?xml version="1.0" encoding="utf-8"?>
<MixxxControllerPreset mixxxVersion="2.4" schemaVersion="1">
    <info>
        <name>DualSense DJ</name>
        <author>DualSense DJ Project</author>
        <description>PS5 DualSense controller mapping</description>
    </info>
    <controller id="DualSense DJ">
        <scriptfiles>
            <file filename="DualSense-DJ-scripts.js" functionprefix="DualSenseDJ"/>
        </scriptfiles>
        <controls>

            <!-- ===== DECK A (MIDI channel 0: status 0xB0 / 0x90) ===== -->

            <control>
                <group>[Channel1]</group><key>volume</key>
                <status>0xB0</status><midino>0x07</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[QuickEffectRack1_[Channel1]]</group><key>super1</key>
                <status>0xB0</status><midino>0x1A</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel1]</group><key>jog</key>
                <status>0xB0</status><midino>0x1B</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[EqualizerRack1_[Channel1]_Effect1]</group><key>parameter1</key>
                <status>0xB0</status><midino>0x20</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[EqualizerRack1_[Channel1]_Effect1]</group><key>parameter2</key>
                <status>0xB0</status><midino>0x21</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[EqualizerRack1_[Channel1]_Effect1]</group><key>parameter3</key>
                <status>0xB0</status><midino>0x22</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel1]</group><key>play</key>
                <status>0x90</status><midino>0x01</midino>
                <options><toggle/></options>
            </control>
            <control>
                <group>[Channel1]</group><key>sync_enabled</key>
                <status>0x90</status><midino>0x03</midino>
                <options><toggle/></options>
            </control>
            <control>
                <group>[Channel1]</group><key>LoadSelectedTrack</key>
                <status>0x90</status><midino>0x04</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel1]</group><key>hotcue_1_activate</key>
                <status>0x90</status><midino>0x10</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel1]</group><key>hotcue_2_activate</key>
                <status>0x90</status><midino>0x11</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel1]</group><key>hotcue_3_activate</key>
                <status>0x90</status><midino>0x12</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel1]</group><key>hotcue_4_activate</key>
                <status>0x90</status><midino>0x13</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel1]</group><key>beatloop_4_toggle</key>
                <status>0x90</status><midino>0x20</midino>
                <options><normal/></options>
            </control>

            <!-- ===== DECK B (MIDI channel 1: status 0xB1 / 0x91) ===== -->

            <control>
                <group>[Channel2]</group><key>volume</key>
                <status>0xB1</status><midino>0x07</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[QuickEffectRack1_[Channel2]]</group><key>super1</key>
                <status>0xB1</status><midino>0x1A</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel2]</group><key>jog</key>
                <status>0xB1</status><midino>0x1B</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[EqualizerRack1_[Channel2]_Effect1]</group><key>parameter1</key>
                <status>0xB1</status><midino>0x20</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[EqualizerRack1_[Channel2]_Effect1]</group><key>parameter2</key>
                <status>0xB1</status><midino>0x21</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[EqualizerRack1_[Channel2]_Effect1]</group><key>parameter3</key>
                <status>0xB1</status><midino>0x22</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel2]</group><key>play</key>
                <status>0x91</status><midino>0x01</midino>
                <options><toggle/></options>
            </control>
            <control>
                <group>[Channel2]</group><key>sync_enabled</key>
                <status>0x91</status><midino>0x03</midino>
                <options><toggle/></options>
            </control>
            <control>
                <group>[Channel2]</group><key>LoadSelectedTrack</key>
                <status>0x91</status><midino>0x04</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel2]</group><key>hotcue_1_activate</key>
                <status>0x91</status><midino>0x10</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel2]</group><key>hotcue_2_activate</key>
                <status>0x91</status><midino>0x11</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel2]</group><key>hotcue_3_activate</key>
                <status>0x91</status><midino>0x12</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel2]</group><key>hotcue_4_activate</key>
                <status>0x91</status><midino>0x13</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel2]</group><key>beatloop_4_toggle</key>
                <status>0x91</status><midino>0x20</midino>
                <options><normal/></options>
            </control>

            <!-- ===== MASTER (channel 0) ===== -->

            <control>
                <group>[Master]</group><key>crossfader</key>
                <status>0xB0</status><midino>0x08</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Library]</group><key>MoveVertical</key>
                <status>0xB0</status><midino>0x30</midino>
                <options><relative/></options>
            </control>

            <!-- ===== EFFECTS (Unit 1 and Unit 2 for default gyro bindings) ===== -->

            <control>
                <group>[EffectRack1_EffectUnit1]</group><key>mix</key>
                <status>0xB0</status><midino>0x40</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[EffectRack1_EffectUnit2]</group><key>parameter1</key>
                <status>0xB0</status><midino>0x41</midino>
                <options><normal/></options>
            </control>

        </controls>
    </controller>
</MixxxControllerPreset>
```

---

## Task 3: Install into Mixxx

```bash
# Copy mapping files to Mixxx controllers directory
cp src/mixxx/midi_mapping.xml ~/.mixxx/controllers/DualSense-DJ.midi.xml
cp src/mixxx/midi_mapping.js ~/.mixxx/controllers/DualSense-DJ-scripts.js
```

Then in Mixxx:
1. Open Preferences → Controllers
2. Select "DualSense DJ" from the device list
3. Load the "DualSense DJ" preset
4. Click Enable
5. Click Apply

---

## Task 4: Verify each mapping in Mixxx

With `python src/main.py` running and Mixxx connected:

| Action | Expected Mixxx response |
|---|---|
| Press L1 | Deck 1 play/pause toggles |
| Press R1 | Deck 2 play/pause toggles |
| Hold L2 trigger | Deck 1 volume rises |
| Slide touchpad left→right | Crossfader moves |
| Press D-pad Up | Deck 1 hot cue 1 set/jump |
| Press Triangle | Deck 2 hot cue 1 set/jump |
| Press Create | Deck 1 beatloop toggles |
| Press L3 | Deck 1 sync toggles |
