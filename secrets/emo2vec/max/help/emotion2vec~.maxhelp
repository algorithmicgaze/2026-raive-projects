{
 "patcher": {
  "fileversion": 1,
  "appversion": {
   "major": 9,
   "minor": 0,
   "revision": 0,
   "architecture": "arm64",
   "modernui": 1
  },
  "rect": [
   100,
   100,
   820,
   470
  ],
  "bglocked": 0,
  "openinpresentation": 0,
  "boxes": [
   {
    "box": {
     "id": "obj-title",
     "maxclass": "comment",
     "text": "emotion2vec~ — realtime speech emotion recognition (emotion2vec+ base on Core ML)",
     "numinlets": 1,
     "numoutlets": 0,
     "outlettype": [],
     "patching_rect": [
      30,
      20,
      740,
      24
     ],
     "fontsize": 14
    }
   },
   {
    "box": {
     "id": "obj-c1",
     "maxclass": "comment",
     "text": "Feed any signal. Every @hop seconds the last 3 s are classified on the GPU. Windows below @gate dBFS are skipped.",
     "numinlets": 1,
     "numoutlets": 0,
     "outlettype": [],
     "patching_rect": [
      30,
      50,
      740,
      20
     ]
    }
   },
   {
    "box": {
     "id": "obj-adc",
     "maxclass": "ezadc~",
     "text": "ezadc~",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "signal",
      "signal"
     ],
     "patching_rect": [
      30,
      100,
      45,
      45
     ]
    }
   },
   {
    "box": {
     "id": "obj-mhop",
     "maxclass": "message",
     "text": "hop 0.5",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      200,
      100,
      50,
      22
     ]
    }
   },
   {
    "box": {
     "id": "obj-mgate",
     "maxclass": "message",
     "text": "gate -60.",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      270,
      100,
      58.5,
      22
     ]
    }
   },
   {
    "box": {
     "id": "obj-mmodel",
     "maxclass": "message",
     "text": "model /path/to/other.mlmodelc",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      350,
      100,
      188.5,
      22
     ]
    }
   },
   {
    "box": {
     "id": "obj-c2",
     "maxclass": "comment",
     "text": "@model: absolute path or a name in the Max search path (default: models/emotion2vec.mlmodelc in this package). The window length is fixed by the model.",
     "numinlets": 1,
     "numoutlets": 0,
     "outlettype": [],
     "patching_rect": [
      120,
      130,
      680,
      20
     ]
    }
   },
   {
    "box": {
     "id": "obj-emo",
     "maxclass": "newobj",
     "text": "emotion2vec~ @hop 0.25 @gate -45.",
     "numinlets": 1,
     "numoutlets": 4,
     "outlettype": [
      "",
      "",
      "float",
      ""
     ],
     "patching_rect": [
      30,
      180,
      214.5,
      22
     ]
    }
   },
   {
    "box": {
     "id": "obj-ms",
     "maxclass": "multislider",
     "text": "multislider",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      ""
     ],
     "patching_rect": [
      30,
      240,
      270,
      120
     ],
     "size": 9,
     "setminmax": [
      0,
      1
     ]
    }
   },
   {
    "box": {
     "id": "obj-c3",
     "maxclass": "comment",
     "text": "angry disgusted fearful happy neutral other sad surprised unknown",
     "numinlets": 1,
     "numoutlets": 0,
     "outlettype": [],
     "patching_rect": [
      30,
      362,
      270,
      20
     ],
     "fontsize": 9
    }
   },
   {
    "box": {
     "id": "obj-set",
     "maxclass": "newobj",
     "text": "prepend set",
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      320,
      220,
      71.5,
      22
     ]
    }
   },
   {
    "box": {
     "id": "obj-lbl",
     "maxclass": "message",
     "text": "",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      320,
      250,
      100,
      22
     ]
    }
   },
   {
    "box": {
     "id": "obj-c4",
     "maxclass": "comment",
     "text": "top emotion",
     "numinlets": 1,
     "numoutlets": 0,
     "outlettype": [],
     "patching_rect": [
      425,
      250,
      71.5,
      22
     ]
    }
   },
   {
    "box": {
     "id": "obj-conf",
     "maxclass": "flonum",
     "text": "flonum",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "bang"
     ],
     "patching_rect": [
      320,
      290,
      60,
      22
     ]
    }
   },
   {
    "box": {
     "id": "obj-c5",
     "maxclass": "comment",
     "text": "top probability",
     "numinlets": 1,
     "numoutlets": 0,
     "outlettype": [],
     "patching_rect": [
      385,
      290,
      97.5,
      22
     ]
    }
   },
   {
    "box": {
     "id": "obj-route",
     "maxclass": "newobj",
     "text": "route db ms",
     "numinlets": 1,
     "numoutlets": 3,
     "outlettype": [
      "",
      "",
      ""
     ],
     "patching_rect": [
      320,
      330,
      71.5,
      22
     ]
    }
   },
   {
    "box": {
     "id": "obj-db",
     "maxclass": "flonum",
     "text": "flonum",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "bang"
     ],
     "patching_rect": [
      320,
      365,
      60,
      22
     ]
    }
   },
   {
    "box": {
     "id": "obj-c6",
     "maxclass": "comment",
     "text": "level (dBFS)",
     "numinlets": 1,
     "numoutlets": 0,
     "outlettype": [],
     "patching_rect": [
      385,
      365,
      78,
      22
     ]
    }
   },
   {
    "box": {
     "id": "obj-lat",
     "maxclass": "flonum",
     "text": "flonum",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "bang"
     ],
     "patching_rect": [
      470,
      365,
      60,
      22
     ]
    }
   },
   {
    "box": {
     "id": "obj-c7",
     "maxclass": "comment",
     "text": "inference (ms)",
     "numinlets": 1,
     "numoutlets": 0,
     "outlettype": [],
     "patching_rect": [
      535,
      365,
      91,
      22
     ]
    }
   },
   {
    "box": {
     "id": "obj-c8",
     "maxclass": "comment",
     "text": "Outlets, left to right: probability list (order above), top emotion, top probability, info messages (db, ms).",
     "numinlets": 1,
     "numoutlets": 0,
     "outlettype": [],
     "patching_rect": [
      30,
      400,
      740,
      20
     ]
    }
   }
  ],
  "lines": [
   {
    "patchline": {
     "source": [
      "obj-adc",
      0
     ],
     "destination": [
      "obj-emo",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-mhop",
      0
     ],
     "destination": [
      "obj-emo",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-mgate",
      0
     ],
     "destination": [
      "obj-emo",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-mmodel",
      0
     ],
     "destination": [
      "obj-emo",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-emo",
      0
     ],
     "destination": [
      "obj-ms",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-emo",
      1
     ],
     "destination": [
      "obj-set",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-set",
      0
     ],
     "destination": [
      "obj-lbl",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-emo",
      2
     ],
     "destination": [
      "obj-conf",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-emo",
      3
     ],
     "destination": [
      "obj-route",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-route",
      0
     ],
     "destination": [
      "obj-db",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-route",
      1
     ],
     "destination": [
      "obj-lat",
      0
     ]
    }
   }
  ]
 }
}
