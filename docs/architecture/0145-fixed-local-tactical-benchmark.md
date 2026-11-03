# Fixed local tactical benchmark

The full-game learner needs a stable opponent with basic tactics. The fixed
`full-game-public-greedy-v1` policy uses only the acting seat's encoded public
observation and pinned displayed-card profiles. It combines attacks, prefers
weak visible enemies, spends defenses, uses useful utilities and terminates
trade and sacrifice selections. It supports solo factions and native teams.
Fog-hidden values and Dream's actual cards cannot enter its decisions.

`simulation full-game-evaluate CHECKPOINT --greedy-baseline` evaluates each
candidate faction against this opponent on the same held-out native seeds.
It is mutually exclusive with `--baseline`. The baseline SHA identifies the
versioned policy name, rather than a neural tensor file. Bump its policy version
when changing released decision behavior.

The baseline remains an approximate, stateless tactical heuristic. Its utility
scores do not establish optimal strategy or official-game fidelity. Training
and promotion gates remain false.

Before this policy was frozen, 512 self-play games across two seeds and four
rosters exposed two zero-MP selection cycles. Both involved a 2-MP miracle and
an available adjacent cost reducer. Reducers now apply whenever needed to
commit affordably. The repeated stress run finished all 512 games with 497
winners and 15 draws, and no truncations. The longest episode used 567 choices.
A direct regression covers the previously cycling selection.

The existing history candidate won 2 of 64 games on each of two benchmark
seed sets before that fix. Those results motivated a separately approved
imitation warm start followed by complete-episode terminal PPO. Subsequent
strength claims require evaluation of the final frozen baseline and candidate.
