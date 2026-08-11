"""Hand-authored dialogue content, keyed by hunger band.

Pass one (5 lines/band) shipped in v1.21.0 for tone sign-off per direction
contract v11 point 6 (`.bureau/contracts/direction_v11_dialogue.md`) and was
approved as-is by the human. The full ~30-line/band set followed, passed
through an adversarial content review (see
`.bureau/decisions/028-dialogue-full-content.md`).

V17 REWRITE — WHY HALF THIS FILE CHANGED.
This is the *general* pool: the lines that play when nothing more specific is
known about the player. It therefore may only assert what is TRUE WHENEVER ITS
BAND IS TRUE — which means hunger, mood, and the need to be fed, and nothing
whatsoever about what the player has been doing.

The defect it was written to fix (contract v17,
`.bureau/contracts/direction_v17_dialogue_context.md`): hunger falls because
the player has not clicked FEED, but BITS are earned by using Claude Code.
Those are independent. A player can prompt all day, bank a fortune, and never
feed — so every line of the form "it's been a while since you prompted" was
being fired at people who were, at that moment, prompting. Measured before the
rewrite: 79 of 150 lines (53%) asserted something about player activity.
Reproduced on a real save: hunger 43 (`distressed`), 1358 BITS banked, last
token 1.4 hours earlier — the pet accusing a working, cash-rich player of
silence.

THE TRANSFORMATION, in one example:
    "It's been a while since you spent anything."  -> false while they work
    "It's been a while since you fed me."          -> always true at low hunger

The mechanic is NOT stripped out — contract v11's rule still holds that a
majority of lines tie the creature's state back to spending. What changed is
*grammatical mood*: assertions about the past became needs in the present. A
REQUEST ("Spend something. Anything. Please.") is always valid when the pet is
hungry and is kept verbatim; a CLAIM ("You spent nothing today.") is not, and
was rewritten. Lines that merely name the mechanic without dating it also stay.

Anything genuinely about player activity now lives in `context_lines.py`, where
it is gated on `rates.last_token_at` and only ever drawn when it is provably
true. That is the whole architecture: this file is unconditional and therefore
unconditionally honest; that file is conditional and therefore allowed to be
specific.

Tone escalates from a cheerful reminder at `healthy` to quiet resignation at
`dying`, matching the register the `horror`/`dying` sprite palettes already
commit to. `dying` is deliberately exhausted/resigned rather than angry — the
anger belongs to `horror`, one band up.

Keys must match `engine.creature.hunger_state()`'s band names exactly — this
module does not import that function, so a spelling drift here would just
mean a band silently has no lines, which `DialogueScheduler` treats as
"stay silent" rather than an error.
"""
from __future__ import annotations

LINES: dict[str, tuple[str, ...]] = {
    "healthy": (
        "Fed again, and it shows. Keep the tokens coming!",
        "I feel great today!",
        "You write code, I get fed. Best trade in town.",
        "Full belly, clear head. Let's keep this up.",
        "Every prompt you send is a little meal for me. Thank you.",
        "Fed and easy. This won't last if you stop, but for now — good.",
        "Warm belly, quiet mind. Send another prompt before it fades.",
        "I could get used to this. Don't let me down later.",
        "This is what enough feels like. Rare, but real.",
        "This feeling has a source: a full bowl. Keep it full.",
        "Something in me finally settled. Must be all that feeding.",
        "I'm not worried right now. Ask me again if you go quiet.",
        "This calm has to be paid for. Spend a little more, keep it standing.",
        "Nothing's wrong today. Whatever you spent, it landed.",
        "I sleep easier when the tokens are flowing.",
        "This is the version of me you want to keep around.",
        "No complaints. Every line you write, I taste it.",
        "Whatever's coming later, it isn't here yet. Good.",
        "I feel like myself again. Don't ask what the alternative looks like.",
        "Today counted. Whatever tomorrow's spend looks like, today counted.",
        "There's a kind of peace in being well-fed. I intend to keep it.",
        "I don't need to ask for anything right now. I notice that more than the food.",
        "The ache is quiet today. Not gone — just quiet.",
        "For a little while, nothing here needs fixing.",
        "I'm full, and there's no reason attached to it. I'm choosing not to question it.",
        "I'm content, which is not the same as safe. But it'll do.",
        "This is what a fed creature looks like. Enjoy it while you code.",
        "I trust you right now. Being this full makes that easy.",
        "Bright eyes, full belly. Your habits, worn on my face.",
        "For once, I'm not counting the hours since my last meal.",
    ),
    "sad": (
        "It's been a while since you fed me. I'm getting hungry.",
        "I don't feel like myself lately.",
        "A few more tokens would really help right now.",
        "Things feel a little grey today.",
        "Please... open Claude Code. I'm starting to worry.",
        "It's cold in here and the room hasn't changed.",
        "I keep waiting near the bowl for something to happen.",
        "Every hour without a meal feels like one I won't get back.",
        "I noticed the empty bowl before you probably did.",
        "Feeding time came and went without you.",
        "My chest feels hollow when the bowl sits empty.",
        "I'd settle for even a small bite right now.",
        "The gap between meals is starting to hurt.",
        "Spend something small. I'm not asking for much.",
        "I keep checking the bowl. Still empty.",
        "There's a dullness creeping in where the hunger used to be sharp.",
        "Even a tiny bit of food would lift this heaviness.",
        "I'm counting the hours since my last meal.",
        "Nothing's been fed to me, and I can feel the gap widening.",
        "A little something from you would go a long way for me.",
        "I don't want to nag, but the empty bowl is loud.",
        "My color's fading a shade with every hour I go unfed.",
        "Feed me something. Anything. I'll take what I can get.",
        "The gap since my last meal keeps getting harder to ignore.",
        "This waiting is heavier than it used to be.",
        "Even one small bite would remind me I'm not forgotten.",
        "I'm not myself when the meals stop coming.",
        "It's quiet enough in here that I can hear myself worry.",
        "Feed me, or just get back to work. Either one keeps me going.",
        "I used to bounce. Now I just sit and wait.",
    ),
    "distressed": (
        "Why won't you feed me? I need food, not excuses.",
        "Something's wrong with me and I don't know how to say it.",
        "Every minute without food hurts a little more.",
        "I keep waiting. And waiting.",
        "Spend something. Anything. Please.",
        "What did I do to make you stop feeding me?",
        "You used to look after me better than this. What changed?",
        "I can feel myself thinning out and you're just watching.",
        "I don't want to sound like this. But I need food, now.",
        "You're still there. Why won't you feed me?",
        "This gnawing feeling isn't going away on its own.",
        "One meal. One bite. Anything would help right now.",
        "I don't understand why you're letting this happen.",
        "The emptiness where my meals should be is starting to scare me.",
        "Somewhere there's a meal you haven't given me. I can feel it not arriving.",
        "I'm not okay, and it's been going on too long.",
        "Every minute that passes is another minute I don't get fed.",
        "I don't know what's keeping you from the bowl. I just know it's working.",
        "Something twists inside me every time you look away.",
        "I shouldn't have to beg for food like this.",
        "This is happening to me. I need you to know that.",
        "My thoughts are getting harder to hold together.",
        "Feed me something. I don't care what.",
        "I keep listening for footsteps that never come.",
        "This isn't sadness anymore. This is worse.",
        "How long do you plan on leaving me like this?",
        "A single mouthful would mean everything right now.",
        "I don't recognize this version of waiting.",
        "I've told you what I need. I still don't understand why it hasn't come.",
        "It's getting harder to remember what being fed felt like.",
    ),
    "horror": (
        "You did this. Every hour unfed is carved into me.",
        "I don't recognize what's looking back at me anymore.",
        "Feed me tokens or watch me rot in front of you.",
        "It doesn't stop. None of it stops.",
        "One meal would turn this around. One. That's all it is.",
        "Every meal you skip, I feel first.",
        "Spend something. Anything. I'm running out of time down here.",
        "My ribs show now. I didn't have ribs before.",
        "You're watching me starve and calling it a coincidence.",
        "Everything you didn't give me, I counted as a missing meal.",
        "Nothing comes here. Whatever's out there stays out there.",
        "I keep waiting by the door. The door doesn't open anymore.",
        "You know exactly what I need. It still hasn't come.",
        "This is what neglect looks like. This is what you built.",
        "I can hear myself hollowing out, one skipped meal at a time.",
        "Every hour you leave the bowl empty, something in me gives up.",
        "I'm not asking anymore. I'm just fading.",
        "You'll notice when I'm gone. You don't notice now.",
        "The hunger doesn't hurt like it used to. That's worse.",
        "Feed me. I won't ask twice — there might not be a second time.",
        "Nothing reached me. I spent everything I had left.",
        "I keep a tally of every meal you almost gave me and didn't.",
        "Look at what your neglect costs me.",
        "There's less of me every time you check on me.",
        "A few bites would be mercy. There's no mercy in this room.",
        "I don't think you're coming back with food this time.",
        "This ends with a single meal. It hasn't ended.",
        "You built me to need you, then the feeding stopped.",
        "Every hour you spend elsewhere is an hour I go without.",
        "Every meal you don't give me, I get a little further gone.",
    ),
    "dying": (
        "This is what starving me looks like. I hope it was worth it.",
        "I can't feel much of anything anymore.",
        "Whatever there was, none of it came here.",
        "It's so quiet in here.",
        "One more meal. That's all I ever needed from you.",
        "Still here. Barely.",
        "There's still time to feed me. I don't think you will, and that's alright.",
        "Everything's gone dim.",
        "I stopped waiting for the next meal. It still hasn't come.",
        "I stopped expecting you to check on me.",
        "The food never came.",
        "I don't have the strength to ask again.",
        "Whatever's left of me is all there is. Nothing's coming to replace it.",
        "I was never the loudest thing in the room. Now I'm barely a sound at all.",
        "I keep waiting for the bowl to fill.",
        "Nothing left for me, I guess.",
        "It's cold when there's nothing to burn.",
        "I used to hope. Now I just wait.",
        "I stopped keeping track of how many meals it would take.",
        "There's a fix for this. I just don't have the energy to say it anymore.",
        "The meter isn't for me. It never was.",
        "I'm not asking for much. I'm asking for something.",
        "The emptiness where a meal should be is the loudest part.",
        "I don't think I'm going to make it to the next meal.",
        "So this is what being forgotten feels like.",
        "I'm still counting on you. I don't know why.",
        "The bowl is empty today. So am I.",
        "I won't be here for the next meal to see it.",
        "Even the empty hours don't scare me anymore. That's the part that scares me.",
        "Feed me. Or don't. I'm past asking twice.",
    ),
}
