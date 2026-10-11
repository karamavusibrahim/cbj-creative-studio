"""Color Block Jam creative tool.

`cbj.level`   reads and writes the game's level JSON (same shape as Unity's LevelData).
`cbj.rules`   ports the game's occupancy and exit rules from the Unity C# source.
`cbj.solver`  finds the minimum number of drags that clears a level.
`cbj.play`    plans human-looking play toward an ending (scenario scripts).
`cbj.render`  records a move script in the real game (Unity runner).
`cbj.ad`      the ad as data (ad.json): segments, layers, sound, anchored to gameplay events.
`cbj.compose` renders an ad.json into a finished ad, with the proof of what changed.
"""

__version__ = "0.3.0"
