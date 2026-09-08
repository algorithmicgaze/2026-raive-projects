{
    "patcher": {
        "fileversion": 1,
        "appversion": {
            "major": 9,
            "minor": 1,
            "revision": 5,
            "architecture": "x64",
            "modernui": 1
        },
        "classnamespace": "box",
        "rect": [ 137.0, 265.0, 1270.0, 913.0 ],
        "boxes": [
            {
                "box": {
                    "id": "obj-lb",
                    "maxclass": "newobj",
                    "numinlets": 1,
                    "numoutlets": 1,
                    "outlettype": [ "bang" ],
                    "patching_rect": [ 30.0, 30.0, 60.0, 22.0 ],
                    "text": "loadbang"
                }
            },
            {
                "box": {
                    "id": "obj-del",
                    "maxclass": "newobj",
                    "numinlets": 2,
                    "numoutlets": 1,
                    "outlettype": [ "bang" ],
                    "patching_rect": [ 30.0, 70.0, 70.0, 22.0 ],
                    "text": "delay 1500"
                }
            },
            {
                "box": {
                    "id": "obj-msg",
                    "maxclass": "message",
                    "numinlets": 2,
                    "numoutlets": 1,
                    "outlettype": [ "" ],
                    "patching_rect": [ 30.0, 110.0, 181.0, 22.0 ],
                    "text": "open mad-as-hell.m4a, loop 1, 1"
                }
            },
            {
                "box": {
                    "id": "obj-sw",
                    "maxclass": "message",
                    "numinlets": 2,
                    "numoutlets": 1,
                    "outlettype": [ "" ],
                    "patching_rect": [ 400.0, 110.0, 77.0, 22.0 ],
                    "text": "startwindow"
                }
            },
            {
                "box": {
                    "id": "obj-sf",
                    "maxclass": "newobj",
                    "numinlets": 2,
                    "numoutlets": 2,
                    "outlettype": [ "signal", "bang" ],
                    "patching_rect": [ 30.0, 160.0, 63.0, 22.0 ],
                    "text": "sfplay~ 1"
                }
            },
            {
                "box": {
                    "id": "obj-emo",
                    "maxclass": "newobj",
                    "numinlets": 1,
                    "numoutlets": 4,
                    "outlettype": [ "list", "symbol", "float", "" ],
                    "patching_rect": [ 30.0, 220.0, 84.0, 22.0 ],
                    "text": "emotion2vec~"
                }
            },
            {
                "box": {
                    "id": "obj-pp",
                    "maxclass": "newobj",
                    "numinlets": 1,
                    "numoutlets": 1,
                    "outlettype": [ "" ],
                    "patching_rect": [ 30.0, 280.0, 91.0, 22.0 ],
                    "text": "prepend probs"
                }
            },
            {
                "box": {
                    "id": "obj-pl",
                    "maxclass": "newobj",
                    "numinlets": 1,
                    "numoutlets": 1,
                    "outlettype": [ "" ],
                    "patching_rect": [ 130.0, 280.0, 91.0, 22.0 ],
                    "text": "prepend label"
                }
            },
            {
                "box": {
                    "id": "obj-pc",
                    "maxclass": "newobj",
                    "numinlets": 1,
                    "numoutlets": 1,
                    "outlettype": [ "" ],
                    "patching_rect": [ 230.0, 280.0, 84.0, 22.0 ],
                    "text": "prepend conf"
                }
            },
            {
                "box": {
                    "id": "obj-udp",
                    "maxclass": "newobj",
                    "numinlets": 1,
                    "numoutlets": 0,
                    "patching_rect": [ 30.0, 340.0, 154.0, 22.0 ],
                    "text": "udpsend 127.0.0.1 7400"
                }
            },
            {
                "box": {
                    "id": "obj-vol",
                    "maxclass": "comment",
                    "numinlets": 1,
                    "numoutlets": 0,
                    "patching_rect": [ 400.0, 140.0, 100.0, 20.0 ],
                    "text": "volume (dB)"
                }
            },
            {
                "box": {
                    "id": "obj-gain",
                    "maxclass": "live.gain~",
                    "numinlets": 2,
                    "numoutlets": 5,
                    "outlettype": [ "signal", "signal", "", "float", "list" ],
                    "parameter_enable": 1,
                    "patching_rect": [ 400.0, 160.0, 48.0, 136.0 ],
                    "saved_attribute_attributes": {
                        "valueof": {
                            "parameter_initial": [ -12.0 ],
                            "parameter_initial_enable": 1,
                            "parameter_longname": "volume",
                            "parameter_mmax": 6.0,
                            "parameter_mmin": -70.0,
                            "parameter_modmode": 3,
                            "parameter_shortname": "volume",
                            "parameter_type": 0,
                            "parameter_unitstyle": 4
                        }
                    },
                    "showname": 0,
                    "varname": "volume"
                }
            },
            {
                "box": {
                    "id": "obj-dac",
                    "maxclass": "ezdac~",
                    "numinlets": 2,
                    "numoutlets": 0,
                    "patching_rect": [ 400.0, 320.0, 45.0, 45.0 ]
                }
            },
            {
                "box": {
                    "id": "obj-err",
                    "maxclass": "newobj",
                    "numinlets": 1,
                    "numoutlets": 1,
                    "outlettype": [ "" ],
                    "patching_rect": [ 550.0, 260.0, 60.0, 22.0 ],
                    "text": "error"
                }
            },
            {
                "box": {
                    "id": "obj-perr",
                    "maxclass": "newobj",
                    "numinlets": 1,
                    "numoutlets": 1,
                    "outlettype": [ "" ],
                    "patching_rect": [ 550.0, 300.0, 112.0, 22.0 ],
                    "text": "prepend maxerror"
                }
            },
            {
                "box": {
                    "id": "obj-vtitle",
                    "maxclass": "comment",
                    "numinlets": 1,
                    "numoutlets": 0,
                    "patching_rect": [ 30.0, 400.0, 200.0, 20.0 ],
                    "text": "class probabilities (0..1)"
                }
            },
            {
                "box": {
                    "id": "obj-ms",
                    "maxclass": "multislider",
                    "numinlets": 1,
                    "numoutlets": 2,
                    "outlettype": [ "", "" ],
                    "parameter_enable": 0,
                    "patching_rect": [ 30.0, 420.0, 450.0, 150.0 ],
                    "setminmax": [ 0.0, 1.0 ],
                    "size": 9,
                    "spacing": 2
                }
            },
            {
                "box": {
                    "id": "obj-c0",
                    "maxclass": "comment",
                    "numinlets": 1,
                    "numoutlets": 0,
                    "fontsize": 10.0,
                    "patching_rect": [ 30.0, 574.0, 50.0, 18.0 ],
                    "text": "angry"
                }
            },
            {
                "box": {
                    "id": "obj-c1",
                    "maxclass": "comment",
                    "numinlets": 1,
                    "numoutlets": 0,
                    "fontsize": 10.0,
                    "patching_rect": [ 80.0, 574.0, 50.0, 18.0 ],
                    "text": "disgust"
                }
            },
            {
                "box": {
                    "id": "obj-c2",
                    "maxclass": "comment",
                    "numinlets": 1,
                    "numoutlets": 0,
                    "fontsize": 10.0,
                    "patching_rect": [ 130.0, 574.0, 50.0, 18.0 ],
                    "text": "fearful"
                }
            },
            {
                "box": {
                    "id": "obj-c3",
                    "maxclass": "comment",
                    "numinlets": 1,
                    "numoutlets": 0,
                    "fontsize": 10.0,
                    "patching_rect": [ 180.0, 574.0, 50.0, 18.0 ],
                    "text": "happy"
                }
            },
            {
                "box": {
                    "id": "obj-c4",
                    "maxclass": "comment",
                    "numinlets": 1,
                    "numoutlets": 0,
                    "fontsize": 10.0,
                    "patching_rect": [ 230.0, 574.0, 50.0, 18.0 ],
                    "text": "neutral"
                }
            },
            {
                "box": {
                    "id": "obj-c5",
                    "maxclass": "comment",
                    "numinlets": 1,
                    "numoutlets": 0,
                    "fontsize": 10.0,
                    "patching_rect": [ 280.0, 574.0, 50.0, 18.0 ],
                    "text": "other"
                }
            },
            {
                "box": {
                    "id": "obj-c6",
                    "maxclass": "comment",
                    "numinlets": 1,
                    "numoutlets": 0,
                    "fontsize": 10.0,
                    "patching_rect": [ 330.0, 574.0, 50.0, 18.0 ],
                    "text": "sad"
                }
            },
            {
                "box": {
                    "id": "obj-c7",
                    "maxclass": "comment",
                    "numinlets": 1,
                    "numoutlets": 0,
                    "fontsize": 10.0,
                    "patching_rect": [ 380.0, 574.0, 50.0, 18.0 ],
                    "text": "surprised"
                }
            },
            {
                "box": {
                    "id": "obj-c8",
                    "maxclass": "comment",
                    "numinlets": 1,
                    "numoutlets": 0,
                    "fontsize": 10.0,
                    "patching_rect": [ 430.0, 574.0, 50.0, 18.0 ],
                    "text": "unknown"
                }
            },
            {
                "box": {
                    "id": "obj-ltitle",
                    "maxclass": "comment",
                    "numinlets": 1,
                    "numoutlets": 0,
                    "patching_rect": [ 520.0, 400.0, 100.0, 20.0 ],
                    "text": "best class"
                }
            },
            {
                "box": {
                    "id": "obj-pset",
                    "maxclass": "newobj",
                    "numinlets": 1,
                    "numoutlets": 1,
                    "outlettype": [ "" ],
                    "patching_rect": [ 520.0, 420.0, 77.0, 22.0 ],
                    "text": "prepend set"
                }
            },
            {
                "box": {
                    "id": "obj-lblm",
                    "maxclass": "message",
                    "numinlets": 2,
                    "numoutlets": 1,
                    "outlettype": [ "" ],
                    "fontsize": 24.0,
                    "patching_rect": [ 520.0, 450.0, 160.0, 36.0 ],
                    "text": ""
                }
            },
            {
                "box": {
                    "id": "obj-ctitle",
                    "maxclass": "comment",
                    "numinlets": 1,
                    "numoutlets": 0,
                    "patching_rect": [ 520.0, 500.0, 100.0, 20.0 ],
                    "text": "confidence"
                }
            },
            {
                "box": {
                    "id": "obj-conf",
                    "maxclass": "flonum",
                    "numinlets": 1,
                    "numoutlets": 2,
                    "outlettype": [ "", "bang" ],
                    "parameter_enable": 0,
                    "patching_rect": [ 520.0, 520.0, 60.0, 22.0 ]
                }
            }
        ],
        "lines": [
            {
                "patchline": {
                    "destination": [ "obj-msg", 0 ],
                    "source": [ "obj-del", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-pc", 0 ],
                    "source": [ "obj-emo", 2 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-conf", 0 ],
                    "source": [ "obj-emo", 2 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-pl", 0 ],
                    "source": [ "obj-emo", 1 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-pset", 0 ],
                    "source": [ "obj-emo", 1 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-pp", 0 ],
                    "source": [ "obj-emo", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-ms", 0 ],
                    "source": [ "obj-emo", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-udp", 0 ],
                    "source": [ "obj-emo", 3 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-perr", 0 ],
                    "source": [ "obj-err", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-del", 0 ],
                    "order": 1,
                    "source": [ "obj-lb", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-sw", 0 ],
                    "order": 0,
                    "source": [ "obj-lb", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-sf", 0 ],
                    "source": [ "obj-msg", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-udp", 0 ],
                    "source": [ "obj-pc", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-udp", 0 ],
                    "source": [ "obj-perr", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-udp", 0 ],
                    "source": [ "obj-pl", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-udp", 0 ],
                    "source": [ "obj-pp", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-lblm", 1 ],
                    "source": [ "obj-pset", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-emo", 0 ],
                    "source": [ "obj-sf", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-gain", 0 ],
                    "source": [ "obj-sf", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-gain", 1 ],
                    "source": [ "obj-sf", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-dac", 0 ],
                    "source": [ "obj-gain", 0 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-dac", 1 ],
                    "source": [ "obj-gain", 1 ]
                }
            },
            {
                "patchline": {
                    "destination": [ "obj-dac", 0 ],
                    "source": [ "obj-sw", 0 ]
                }
            }
        ],
        "parameters": {
            "obj-gain": [ "volume", "volume", 0 ],
            "parameterbanks": {
                "0": {
                    "index": 0,
                    "name": "",
                    "parameters": [ "-", "-", "-", "-", "-", "-", "-", "-" ]
                }
            },
            "inherited_shortname": 1
        },
        "autosave": 0
    }
}
