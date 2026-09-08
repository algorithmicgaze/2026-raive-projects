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
   520.0,
   360.0
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
     "text": "rand-range: a random float between min and max.\nInlets: bang (left), min (middle), max (right). Outlet: the value.",
     "id": "obj-1",
     "patching_rect": [
      20,
      15,
      480,
      36
     ],
     "linecount": 2
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "inlet",
     "id": "obj-2",
     "patching_rect": [
      20,
      70,
      40,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "inlet",
     "id": "obj-3",
     "patching_rect": [
      160,
      70,
      40,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "inlet",
     "id": "obj-4",
     "patching_rect": [
      300,
      70,
      40,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "bang = make a new value",
     "id": "obj-5",
     "patching_rect": [
      70,
      70,
      90,
      36
     ],
     "linecount": 2
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "min",
     "id": "obj-6",
     "patching_rect": [
      210,
      70,
      40,
      21
     ],
     "linecount": 1
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "max",
     "id": "obj-7",
     "patching_rect": [
      350,
      70,
      40,
      21
     ],
     "linecount": 1
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "random 10000",
     "id": "obj-8",
     "patching_rect": [
      20,
      120,
      98,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "random gives an integer from 0 to 9999",
     "id": "obj-9",
     "patching_rect": [
      130,
      120,
      260,
      21
     ],
     "linecount": 1
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "/ 10000.",
     "id": "obj-10",
     "patching_rect": [
      20,
      160,
      70,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "divide by 10000. (with the dot, so the result is a float): u = 0.0 ... 0.9999",
     "id": "obj-11",
     "patching_rect": [
      130,
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
     "text": "expr $f2 + $f1 * ($f3 - $f2)",
     "id": "obj-12",
     "patching_rect": [
      20,
      220,
      210,
      22
     ]
    }
   },
   {
    "box": {
     "maxclass": "comment",
     "text": "value = min + u * (max - min).\n$f1 = u (left inlet, hot: it makes the output), $f2 = min, $f3 = max.\nu = 0 gives min, u = 1 gives max, in between it scales linearly.",
     "id": "obj-13",
     "patching_rect": [
      20,
      250,
      480,
      51
     ],
     "linecount": 3
    }
   },
   {
    "box": {
     "maxclass": "newobj",
     "text": "outlet",
     "id": "obj-14",
     "patching_rect": [
      20,
      310,
      40,
      22
     ]
    }
   }
  ],
  "lines": [
   {
    "patchline": {
     "source": [
      "obj-2",
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
      "obj-8",
      0
     ],
     "destination": [
      "obj-10",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-10",
      0
     ],
     "destination": [
      "obj-12",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-3",
      0
     ],
     "destination": [
      "obj-12",
      1
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
      "obj-12",
      2
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-12",
      0
     ],
     "destination": [
      "obj-14",
      0
     ]
    }
   }
  ],
  "dependency_cache": [],
  "autosave": 0
 }
}