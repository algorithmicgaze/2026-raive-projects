{
 "patcher": {
  "fileversion": 1,
  "appversion": {
   "major": 8,
   "minor": 6,
   "revision": 0,
   "architecture": "x64",
   "modernui": 1
  },
  "classnamespace": "box",
  "rect": [
   100.0,
   100.0,
   760.0,
   560.0
  ],
  "bglocked": 0,
  "openinpresentation": 0,
  "default_fontsize": 12.0,
  "default_fontface": 0,
  "default_fontname": "Arial",
  "gridonopen": 1,
  "gridsize": [
   15.0,
   15.0
  ],
  "gridsnaponopen": 1,
  "objectsnaponopen": 1,
  "statusbarvisible": 2,
  "toolbarvisible": 1,
  "lefttoolbarpinned": 0,
  "toptoolbarpinned": 0,
  "righttoolbarpinned": 0,
  "bottomtoolbarpinned": 0,
  "toolbars_unpinned_last_save": 0,
  "tallnewobj": 0,
  "boxanimatetime": 200,
  "enablehscroll": 1,
  "enablevscroll": 1,
  "devicewidth": 0.0,
  "description": "",
  "digest": "",
  "tags": "",
  "style": "",
  "subpatcher_template": "",
  "assistshowspatchername": 0,
  "boxes": [
   {
    "box": {
     "maxclass": "comment",
     "text": "grain-voice: one grain. poly~ loads this patch once per voice.\npoly~ sends 'note start size ratio' to the free voice; the word 'note' is stripped, so the inlet gets the list: start (ms in the buffer), size (ms), ratio (pitch, 1 = original).",
     "id": "obj-1",
     "patching_rect": [
      20,
      15,
      700,
      51
     ],
     "linecount": 3
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "in 1",
     "id": "obj-2",
     "patching_rect": [
      20,
      80,
      40,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "a poly~ voice uses 'in' and 'out~', not inlet and outlet~. poly~ only sees those.",
     "id": "obj-3",
     "patching_rect": [
      70,
      80,
      500,
      36
     ],
     "linecount": 2
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "t l b",
     "id": "obj-4",
     "patching_rect": [
      20,
      120,
      49,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "trigger fires right to left: first the bang (mark this voice busy), then the list",
     "id": "obj-5",
     "patching_rect": [
      90,
      120,
      480,
      36
     ],
     "linecount": 2
    }
   },
   {
    "box": {
     "maxclass": "message",
     "text": "mute 0, 1",
     "id": "obj-6",
     "patching_rect": [
      300,
      160,
      77,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "mute 0 = switch this voice's DSP on, 1 = tell poly~ this voice is busy",
     "id": "obj-7",
     "patching_rect": [
      380,
      160,
      360,
      36
     ],
     "linecount": 2
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "thispoly~",
     "id": "obj-8",
     "patching_rect": [
      300,
      400,
      77,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "unpack 0. 0. 0.",
     "id": "obj-9",
     "patching_rect": [
      20,
      160,
      119,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "start",
     "id": "obj-10",
     "patching_rect": [
      20,
      185,
      40,
      21
     ],
     "linecount": 1
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "size",
     "id": "obj-11",
     "patching_rect": [
      70,
      185,
      40,
      21
     ],
     "linecount": 1
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "ratio",
     "id": "obj-12",
     "patching_rect": [
      130,
      185,
      40,
      21
     ],
     "linecount": 1
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "POSITION: the read head runs from start to end in 'size' ms.\nend = start + size * ratio. ratio 2 covers twice the distance in the same time: one octave up. ratio 0.5: one octave down.",
     "id": "obj-13",
     "patching_rect": [
      20,
      215,
      320,
      81
     ],
     "linecount": 5
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "t f f",
     "id": "obj-14",
     "patching_rect": [
      20,
      240,
      49,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "right outlet first: compute 'end' before 'start' goes into the second pak",
     "id": "obj-15",
     "patching_rect": [
      100,
      240,
      260,
      36
     ],
     "linecount": 2
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "pak 0. 0. 0.",
     "id": "obj-16",
     "patching_rect": [
      100,
      270,
      98,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "expr $f1 + $f2 * $f3",
     "id": "obj-17",
     "patching_rect": [
      100,
      300,
      154,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "pak 0. 0. 0.",
     "id": "obj-18",
     "patching_rect": [
      20,
      330,
      98,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "pak collects start, end, size into one list",
     "id": "obj-19",
     "patching_rect": [
      150,
      330,
      240,
      36
     ],
     "linecount": 2
    }
   },
   {
    "box": {
     "maxclass": "message",
     "text": "$1, $2 $3",
     "id": "obj-20",
     "patching_rect": [
      20,
      360,
      77,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "line~ message: 'jump to $1, then go to $2 in $3 ms'",
     "id": "obj-21",
     "patching_rect": [
      110,
      360,
      300,
      36
     ],
     "linecount": 2
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "line~",
     "id": "obj-22",
     "patching_rect": [
      20,
      390,
      49,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "play~ ringbuf",
     "id": "obj-23",
     "patching_rect": [
      20,
      420,
      105,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "play~ reads the buffer at the position (in ms) it gets as a signal",
     "id": "obj-24",
     "patching_rect": [
      130,
      420,
      300,
      36
     ],
     "linecount": 2
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "ENVELOPE: a ramp 0 -> 1 over the same 'size' ms. trapezoid~ turns the ramp into a short fade in (0 to 0.1 of the ramp), full level, and a short fade out (0.9 to 1). Multiply the audio by this so the grain has no clicks.",
     "id": "obj-25",
     "patching_rect": [
      380,
      215,
      360,
      66
     ],
     "linecount": 4
    }
   },
   {
    "box": {
     "maxclass": "message",
     "text": "0, 1 $1",
     "id": "obj-26",
     "patching_rect": [
      380,
      270,
      63,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "line~",
     "id": "obj-27",
     "patching_rect": [
      380,
      300,
      49,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "trapezoid~ 0.1 0.9",
     "id": "obj-28",
     "patching_rect": [
      380,
      330,
      140,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "*~",
     "id": "obj-29",
     "patching_rect": [
      20,
      460,
      28,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "out~ 1",
     "id": "obj-30",
     "patching_rect": [
      20,
      500,
      56,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "meter~",
     "id": "obj-31",
     "patching_rect": [
      90,
      460,
      20,
      100
     ]
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "level of this grain (open a voice with the 'open' message in the main patch)",
     "id": "obj-32",
     "patching_rect": [
      120,
      470,
      300,
      36
     ],
     "linecount": 2
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "FREE: after 'size' ms the grain is done: mute the DSP (mute 1) and tell poly~ the voice is free (0).",
     "id": "obj-33",
     "patching_rect": [
      300,
      440,
      440,
      36
     ],
     "linecount": 2
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "t b f",
     "id": "obj-34",
     "patching_rect": [
      520,
      270,
      49,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "f sets the delay time (right inlet), then b starts the delay",
     "id": "obj-35",
     "patching_rect": [
      580,
      270,
      170,
      51
     ],
     "linecount": 3
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "delay 100",
     "id": "obj-36",
     "patching_rect": [
      520,
      310,
      77,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "message",
     "text": "mute 1, 0",
     "id": "obj-37",
     "patching_rect": [
      520,
      350,
      77,
      22
     ]
    }
   }
  ],
  "lines": [
   {
    "patchline": {
     "source": [
      "obj-29",
      0
     ],
     "destination": [
      "obj-31",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-2",
      0
     ],
     "destination": [
      "obj-4",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-4",
      1
     ],
     "destination": [
      "obj-6",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      0
     ],
     "destination": [
      "obj-8",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-4",
      0
     ],
     "destination": [
      "obj-9",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-9",
      0
     ],
     "destination": [
      "obj-14",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-14",
      1
     ],
     "destination": [
      "obj-16",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-9",
      1
     ],
     "destination": [
      "obj-16",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-9",
      2
     ],
     "destination": [
      "obj-16",
      2
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-16",
      0
     ],
     "destination": [
      "obj-17",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-14",
      0
     ],
     "destination": [
      "obj-18",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-17",
      0
     ],
     "destination": [
      "obj-18",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-9",
      1
     ],
     "destination": [
      "obj-18",
      2
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-18",
      0
     ],
     "destination": [
      "obj-20",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-20",
      0
     ],
     "destination": [
      "obj-22",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-22",
      0
     ],
     "destination": [
      "obj-23",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-9",
      1
     ],
     "destination": [
      "obj-26",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-26",
      0
     ],
     "destination": [
      "obj-27",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-27",
      0
     ],
     "destination": [
      "obj-28",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-23",
      0
     ],
     "destination": [
      "obj-29",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-28",
      0
     ],
     "destination": [
      "obj-29",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-29",
      0
     ],
     "destination": [
      "obj-30",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-9",
      1
     ],
     "destination": [
      "obj-34",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-34",
      1
     ],
     "destination": [
      "obj-36",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-34",
      0
     ],
     "destination": [
      "obj-36",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-36",
      0
     ],
     "destination": [
      "obj-37",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-37",
      0
     ],
     "destination": [
      "obj-8",
      0
     ]
    }
   }
  ],
  "dependency_cache": [],
  "autosave": 0
 }
}