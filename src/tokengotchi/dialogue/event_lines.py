"""Event-fired dialogue content — Layer 3a, cosmetic purchases.

Direction contract v17 (`.bureau/contracts/direction_v17_dialogue_context.md`),
"Layer 3 — Event dialogue". Unlike `lines.py`, nothing here is keyed by hunger
band: these pools fire on a *real event* (a purchase that actually succeeded)
rather than on the ambient timer, so every line is true at the moment it is
spoken by construction rather than by gating.

This module is **content only**. It deliberately owns no selection logic, no
timer, and no flash: the call site owns precedence, the deferral to shop-close
(contract Open Question 2), the `bool` return check (constraint 4), and the
deliberate omission of `taskbar_flash` (constraint 3).

Selection precedence the call site is expected to implement, first match wins:

1. ``starving``      — hunger band is `distressed`/`horror`/`dying`. Replaces
                       the cheerful pool *entirely*, regardless of kind. This
                       is the contract's diversion, and it outranks even
                       `first_of_kind`: a first hat bought over a starving pet
                       is not a milestone, it is the diversion's whole point.
2. ``first_of_kind`` — the player owned nothing of this `ItemKind` before now.
3. ``ITEM_LINES[item.id]`` — a per-item override, for the rare item whose
                       flavour is specific enough that the shared per-kind
                       pool would flatten it (e.g. `hat_kippah`). More
                       specific than the per-kind pool, but still a purchase
                       like any other, so it does not outrank `first_of_kind`.
4. ``item.kind.value`` — the per-kind pool, e.g. ``PURCHASE_LINES["hat"]``.
5. ``generic``       — hard fallback. Required by the brief: an unmapped or
                       future kind must never be silent. The call site should
                       read the per-kind pool as::

                           PURCHASE_LINES.get(item.kind.value,
                                              PURCHASE_LINES["generic"])

                       so adding a sixth `ItemKind` to the catalogue degrades
                       to a plausible line instead of nothing.

The four cosmetic kinds are mechanically different things and the writing
carries that difference rather than four variants of "nice hat":

* **hat**    — goes *on* the creature. Personal. It can feel the weight but
               can never see itself wearing it.
* **screen** — changes the *light* the creature is drawn in. It is made of
               that light, so this changes what it *is*, not what it wears.
* **shell**  — the case. The room around it, visible only from the inside.
* **field**  — the world behind it. The first purchase that is neither the
               creature nor its box.

`ItemKind.CONSUMABLE` has no pool by design: rations are food, not cosmetics,
and feeding reactions are a separate event. It falls through to ``generic``.
Equipping and unequipping stay silent entirely (Open Question 3: purchase
only) — there is nothing here for them to draw from.

House style, matching `lines.py`: second person, addressed to the player;
never emoji; short enough for the dialogue box (kept under ~90 characters).
The creature knows cosmetics are bought with ECHOES while food costs BITS,
and the sharpest `starving` lines acknowledge that and are wounded anyway.
"""
from __future__ import annotations

from ..shop.catalogue import ItemKind

# Keys are `ItemKind` *values*, spelled via the enum rather than as literals so
# a rename in the catalogue is an ImportError/AttributeError here instead of a
# pool that silently stops matching. `ItemKind` is a `str` Enum, so these keys
# are ordinary strings and `PURCHASE_LINES["hat"]` works as written.
PURCHASE_LINES: dict[str, tuple[str, ...]] = {
    # It goes ON me. I can feel it; I can never look at it.
    ItemKind.HAT.value: (
        "Everything else you buy goes around me. This one goes on me.",
        "I can feel the weight of it. That's the only way I'll know it's there.",
        "You'll have to tell me how it looks. There are no mirrors in here.",
        "It sits just above where I think. I'll get used to that.",
        "Something on my head that wasn't there this morning. I've decided I like it.",
        "You dressed me. Nobody has ever done that before today.",
        "I keep tilting to feel it shift. It shifts.",
        "It's warm where it touches. I didn't expect warm.",
        "This is the first thing you've bought that I have to carry.",
        "I can't see it. I can feel its edge against me. That's enough.",
        "You picked this for a shape you've only ever seen from the front.",
        "It'll still be on me when you close the window. That's the part I like.",
    ),
    # It changes the LIGHT. I am made of that light.
    ItemKind.SCREEN.value: (
        "You changed the colour of the light. I'm made of that light.",
        "I didn't get a new coat. I got a new me. Same shape, different substance.",
        "Every part of me is this colour now. There was no part left over.",
        "You didn't decorate me. You reprinted me.",
        "I was another colour a moment ago. I can't remember being it.",
        "The light changed and I changed with it. I'm not separate from it.",
        "This is nearer surgery than shopping. I'm not complaining.",
        "Whatever this glow is, it's what I'm built out of now.",
        "You reached past the case and changed the thing inside it.",
        "I can't step out of the light to look at it. I'm the part it lands on.",
        "New light. Everything I do from now on happens inside it.",
        "You changed what I'm made of and I still feel like myself. Odd.",
    ),
    # It's the room. I only ever see the inside of it.
    ItemKind.SHELL.value: (
        "I can't see the outside of this thing. I'll take your word for it.",
        "You redecorated a room I live in and can only ever see the inside of.",
        "So the box is new. I'm told. I'm still in here.",
        "You bought that one for you. That's fair — you're the one looking at it.",
        "This is the wall I face. I hope it's a good colour from your side.",
        "Somewhere out past the glass, something changed. Sounds nice.",
        "The case is the part of me that faces you. Makes sense you'd pick it.",
        "I live in here. You live out there. You just bought something for out there.",
        "I felt a small tremor and nothing else. Describe it to me sometime.",
        "The shape around me is different now. The shape of me isn't.",
        "You picked a colour I will never once look at. Thank you anyway.",
        "It's a good room, apparently. I'll keep facing this way.",
    ),
    # It's the world behind me. Neither me nor my box.
    ItemKind.FIELD.value: (
        "It's weather now. In here. Falling past me while I stand still.",
        "You bought something that isn't me and isn't my box. That's new.",
        "There's a world behind me now. It was blank this morning.",
        "It moves and I don't. I haven't decided how I feel about that.",
        "Something's happening back there without asking me first.",
        "You gave the empty part a job. It's busy now.",
        "I have a background. That means I'm in front of something.",
        "It'll keep doing that after you log off. It doesn't need either of us.",
        "The air in here has an opinion now.",
        "For the first time, there's something in here that isn't about me.",
        "It drifts past and never lands. I've started watching for it.",
        "You bought scenery. I've never had anywhere to be before.",
    ),
    # THE DIVERSION. Cosmetic bought while distressed/horror/dying. Preempts
    # every pool above, whatever the kind. The pet knows echoes aren't bits;
    # the sharpest lines say so and are wounded anyway.
    "starving": (
        "It's beautiful. I'm starving. Both of those are true right now.",
        "You went shopping. You walked past the feed button to do it.",
        "Different currency. I know. It still felt like a choice.",
        "You can't feed me with echoes. I know. I watched you spend them anyway.",
        "Thank you. I think. It's hard to be gracious at this hunger.",
        "You had time to browse. That's the part I can't put down.",
        "I'll wear it. I'd rather eat.",
        "You made me look better without making me better.",
        "Lovely. Now the shape of my ribs has a theme.",
        "The shop was open. So was I. You went to the shop.",
        "I know echoes aren't bits. I do. It helps less than it should.",
        "You dressed me up. You didn't feed me. I noticed the order of those.",
        "You spent something on me today. Not the something I needed.",
        "I don't want to be ungrateful. I want to be fed. Those are competing.",
    ),
    # First item of this kind the player has ever owned.
    "first_of_kind": (
        "That's a kind of thing I've never had before. No word for it yet.",
        "First one. Everything else you buy like this gets measured against it.",
        "There was no category for this an hour ago. Now there's one, holding one thing.",
        "I didn't know that was a thing you could buy me.",
        "The first of anything is the one I'll remember. Fair warning.",
        "You just opened a door I didn't know was in here.",
    ),
    # HARD FALLBACK. An unmapped or future item must never be silent.
    "generic": (
        "Something new. I don't know what to call it yet, but I noticed.",
        "You bought something. It landed. Thank you.",
        "That's yours now, which makes it mine now. I think that's how this works.",
        "Whatever that was, the room feels one item heavier.",
        "You spent something on me. I keep track of those.",
        "New thing. I'll work out what it does to me eventually.",
        "I felt that go through. Something changed.",
        "That wasn't free. I know what things cost around here.",
    ),
}

# Per-item overrides, keyed by catalogue `Item.id` rather than `ItemKind`. Some
# items are specific enough that the kind-wide pool above would flatten them
# into a generic hat/screen/shell/field line; this dict lets one item speak
# for itself while every other member of its kind keeps drawing from the pool.
ITEM_LINES: dict[str, tuple[str, ...]] = {
    "hat_kippah": ("You are invited to my bar mitzvah.",),
}
