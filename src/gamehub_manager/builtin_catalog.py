"""Built-in catalog of free / open-source games with direct Windows download links."""
from __future__ import annotations

BUILTIN_CATALOG: list[dict] = [
    {
        "title": "OpenTTD",
        "description": "Open-source transport tycoon simulation. Build rail, road, air and water networks.",
        "urls": ["https://cdn.openttd.org/openttd-releases/14.1/openttd-14.1-windows-win64.exe"],
        "tags": ["simulation", "strategy"],
    },
    {
        "title": "SuperTuxKart",
        "description": "Kart racing game with Tux and friends. Single player, split-screen and online.",
        "urls": ["https://github.com/supertuxkart/stk-code/releases/download/1.4/SuperTuxKart-1.4-win-x86_64.zip"],
        "tags": ["racing", "arcade"],
    },
    {
        "title": "Warzone 2100",
        "description": "Post-apocalyptic real-time strategy game with a full campaign and skirmish modes.",
        "urls": ["https://github.com/Warzone2100/warzone2100/releases/download/4.4.2/warzone2100_4.4.2_windows_x64.exe"],
        "tags": ["rts", "strategy"],
    },
    {
        "title": "Minetest",
        "description": "Infinite-world block sandbox game with survival and creative modes, fully moddable.",
        "urls": ["https://github.com/minetest/minetest/releases/download/5.9.0/minetest-5.9.0-win64.zip"],
        "tags": ["sandbox", "survival"],
    },
    {
        "title": "Battle for Wesnoth",
        "description": "Turn-based fantasy strategy game with a huge collection of campaigns and maps.",
        "urls": ["https://sourceforge.net/projects/wesnoth/files/wesnoth-1.18/wesnoth-1.18.2/wesnoth-1.18.2-win64.exe/download"],
        "tags": ["strategy", "turn-based", "fantasy"],
    },
    {
        "title": "Xonotic",
        "description": "Fast-paced open-source first-person shooter with crisp movement and online play.",
        "urls": ["https://dl.xonotic.org/xonotic-0.8.6.zip"],
        "tags": ["fps", "shooter"],
    },
    {
        "title": "0 A.D.",
        "description": "Historical real-time strategy game spanning civilisations from 500 BC to 500 AD.",
        "urls": ["https://releases.wildfiregames.com/0ad-0.0.27-alpha-win32.exe"],
        "tags": ["rts", "historical"],
    },
    {
        "title": "FreeCiv",
        "description": "Multiplayer strategy game inspired by the history of human civilisation.",
        "urls": ["https://github.com/freeciv/freeciv/releases/download/S3_1_0/freeciv-3.1.0-win64-gtk3.22.exe"],
        "tags": ["strategy", "4x"],
    },
    {
        "title": "Teeworlds",
        "description": "Retro-style online multiplayer 2D shooter. Simple, fast and very addictive.",
        "urls": ["https://github.com/teeworlds/teeworlds/releases/download/0.7.5/teeworlds-0.7.5-win64.zip"],
        "tags": ["shooter", "2d", "multiplayer"],
    },
    {
        "title": "AssaultCube",
        "description": "Realistic-ish first-person shooter set in urban environments. Low system requirements.",
        "urls": ["https://github.com/assaultcube/AC/releases/download/v1.3.0.2/AssaultCube_v1.3.0.2.exe"],
        "tags": ["fps", "shooter"],
    },
    {
        "title": "Endless Sky",
        "description": "Space exploration and trading game in the tradition of Elite and Escape Velocity.",
        "urls": ["https://github.com/endless-sky/endless-sky/releases/download/v0.10.9/endless-sky-win64-0.10.9.exe"],
        "tags": ["space", "rpg", "trading"],
    },
    {
        "title": "Veloren",
        "description": "Multiplayer voxel RPG inspired by Cube World and Legend of Zelda. Always free.",
        "urls": ["https://download.veloren.net/latest/windows/x86_64/stable"],
        "tags": ["rpg", "voxel", "multiplayer"],
    },
    {
        "title": "Unknown Horizons",
        "description": "Real-time strategy and city builder with a strong focus on economy and trade.",
        "urls": ["https://github.com/unknown-horizons/unknown-horizons/releases/download/2019.1/UnknownHorizons-2019.1.exe"],
        "tags": ["rts", "city-builder"],
    },
    {
        "title": "FlightGear",
        "description": "Professional open-source flight simulator with hundreds of aircraft and global scenery.",
        "urls": ["https://sourceforge.net/projects/flightgear/files/release-2020.3/FlightGear-2020.3.19.exe/download"],
        "tags": ["simulation", "flight"],
    },
    {
        "title": "The Dark Mod",
        "description": "Standalone stealth game in a dark Victorian/steampunk world, inspired by Thief.",
        "urls": ["https://www.thedarkmod.com/download-the-mod/"],
        "tags": ["stealth", "action"],
    },
]
