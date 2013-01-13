# -*- coding: utf-8 -*-
"""
  Script for finding out scouting patterns for overlords and scans.

  Requires 
  - sc2reader (github.com/GraylinKim/sc2reader)
  - pil (www.pythonware.com/products/pil/)
"""

import argparse
import hashlib
import os
import cPickle as pickle
import pprint
import sc2reader
import sys

from PIL import Image, ImageDraw
from datetime import datetime
from sc2reader.events import *
from sc2reader.objects import *
from StringIO import StringIO

# (y_offset, w, h)
scanner_radius = 13
heatmap_colors = list(reversed(["rgb(255, 0, 0)", 
                                "rgb(255, 78, 0)", 
                                "rgb(255, 157, 0)", 
                                "rgb(255, 235, 0)", 
                                "rgb(196, 255, 0)", 
                                "rgb(118, 255, 0)", 
                                "rgb(39, 255, 0)", 
                                "rgb(0, 255, 39)", 
                                "rgb(0, 255, 118)", 
                                "rgb(0, 255, 196)", 
                                "rgb(0, 235, 255)", 
                                "rgb(0, 157, 255)", 
                                "rgb(0, 78, 255)", 
                                "rgb(0, 0, 255)",
                                None]))
heatmap_values = [(float(i) / (len(heatmap_colors)-1), heatmap_colors[i]) 
                  for i in range(len(heatmap_colors))]

def parse_args(args):
    parser = argparse.ArgumentParser(
        description="")

    parser.add_argument("FILES", type=str, nargs='+',
        help="Files to analyse.")
    parser.add_argument("--verbose", "-v", dest="debug", 
        default=False, action="store_true", 
        help="Show debug info.")
    parser.add_argument("--max-time", "-t", metavar="SECONDS", type=int,
        dest="seconds", default=300,
        help="Number of seconds to analyse in each match. Use 0 if you want the entire replay. Note that a higher number will make the script less accurate. Default is 300 (5 minutes).")
    parser.add_argument("--heatmap", default=False, action="store_true",
        help="Generate a heatmap of the scans")
    parser.add_argument("--image-scale", default=None, type=float, dest="imscale",
        help="The scale of all minimap images.")
    parser.add_argument('--output-dir', '-o', dest='dir', default='outputs', type=str,
        help="Directory to save stuff to.")
    parser.add_argument("--no-cache", dest="cache", 
        action="store_false", default=True,
        help="Do not cache the calculation. This prevents both loading and saving to the cache.")

    return parser.parse_args(args)

log = None

def main(args):
    global log
                
    if args.debug:
        def log_temp(msg):
            print "[{}]: DEBUG: {}".format(datetime.now().time(), msg)
        log = log_temp
    else:
        log = lambda x: x
    log("Script start")
    
    # Check cache
    if args.cache:
        m = hashlib.md5()
        m.update(pickle.dumps({"files": 
                               [os.path.abspath(f) for f in args.FILES],
                               "seconds": args.seconds}))
        cache_hash = m.hexdigest()
        del m

        cache_path = os.path.join(".cache", cache_hash)
        
        if os.path.exists(".cache") and os.path.exists(cache_path):
            f = open(cache_path, "r")
            data = pickle.load(f)
            f.close()
        else:
            data = do_stuff(args)
    else:
        data = do_stuff(args)
        
    if args.cache:
        if not os.path.exists(".cache"):
            os.mkdir(".cache")
        f = open(cache_path, "w")
        pickle.dump(data, f)
        f.close()

    if not os.path.exists(args.dir):
        os.mkdir(args.dir)

    for hash in data:
        image = load_minimap(data[hash]["minimap"], data[hash]["bounds"], scale=args.imscale)
        trans = Translation(data[hash]["bounds"], image.size)
        if args.heatmap:
            log("Generating heatmap")
            heatim = create_scan_heatmap(image, trans, data[hash]["terran"])
            log("Saving heatmap")
            heatim.save(os.path.join(args.dir, "heatmap_{}.bmp".format(hash)))
        draw_scans(image, trans, data[hash]["terran"]).save("scans.bmp")

def do_stuff(args):
    replays = sc2reader.load_replays(args.FILES, options={"load_map":True, "debug":True})
    
    data = {}
    for replay in replays:
        log("New replay")

        terrans = [{'player': p, 
                    'selected': None, 
                    'scans': []} 
                   for p in replay.players if p.play_race == "Terran"]
        zergs = [{'player': p, 
                  'selected': None} 
                 for p in replay.players if p.play_race == "Zerg"]
                
        for event in replay.events:
            if args.seconds != 0 and event.time.total_seconds() > args.seconds:
                break  

            for t in terrans:
                if t["player"].pid != event.pid:
                    continue
                if isinstance(event, SelectionEvent):
                    t["selected"] = event.objects
                elif isinstance(event, LocationAbilityEvent):

                    if event.ability_name == "CalldownScannerSweep":
                        log(event)
                        log(event.location)
                        t["scans"].append((event.frame,) + event.location)
        
        if not replay.map_hash in data:
            data[replay.map_hash] = {
                "map": replay.map.name, 
                "minimap": replay.map.minimap, 
                "bounds": load_bounds(replay.map.archive),
                "zerg":[], 
                "terran":[]}
            log("Map added")
            log(data[replay.map_hash]["bounds"])
        for t in terrans:
            data[replay.map_hash]["terran"].extend(t["scans"])

    return data


def load_minimap(tgadata, bounds, scale=None):
    image = Image.open(StringIO(tgadata))

    center = (image.size[0] / 2.0, image.size[1] / 2.0)
    playablew = bounds[2][2] - bounds[2][0]
    playableh = bounds[2][3] - bounds[2][1]

    image = image.crop((int(center[0] - (playablew / 2.0)),
                        int(center[1] - (playableh / 2.0)),
                        int(center[0] + (playablew / 2.0)),
                        int(center[1] + (playableh / 2.0))))
    if not (scale is None):
        return image.resize((int(image.size[0] * scale), int(image.size[1] * scale)))
    return image

def test_drawing(image):
    
    draw = ImageDraw.Draw(image)
    
    draw.line((0, 0) + image.size, fill="red")
    draw.line((0, image.size[1], image.size[0], 0), fill="green")
    draw.ellipse((0,0)+image.size, outline="red", fill="#ff0000")
    del draw

def draw_scans(image, translation, scans):
    
    draw = ImageDraw.Draw(image)

    for scan in scans:
        (x, y) = (scan[1], scan[2])
        
        
        bounds = translation.box_map2mini((x - scanner_radius, 
                                           y - scanner_radius, 
                                           x + scanner_radius, 
                                           y + scanner_radius))
        
        #print bounds

        draw.ellipse(bounds, outline="red", fill="red")
        
        
    del draw
    return image

def create_scan_heatmap(image, translation, scans, copy=True):
    # Se how many times each point is hit by a scan
    # Every pixel is mapped to a point which is then checked

    map_size = translation.playable_size
    bl = translation.bl

    points = [[(col, row), 0]
              for col in range(translation.minimap[0]) 
              for row in range(translation.minimap[1])]

    for scan in scans:
        for point in points:
            if inside(translation.mini2map(point[0]), (scan[1], scan[2])):
                point[1] += 1

    # Normalize
    maximum = max(p[1] for p in points)
    if maximum == 0:
        return image.copy() if copy else image
    points = [(point[0], float(point[1]) / maximum) for point in points]
    points.sort(key=lambda x: x[1])

    # Color
    points = [(point[0], get_color(point[1])) for point in points]

    im = None
    if copy:
        im = image.copy()
    else:
        im = image

    draw = ImageDraw.Draw(im)

    for (pos, color) in points:
        if color is None:
            continue
        draw.point(pos, fill=color)
        
    del draw
    return im


def get_color(value):
    for (t, color) in heatmap_values:
        if value <= t:
            return color
    return None

def inside(point, scan_center):
    d = (scan_center[0] - point[0]) ** 2 + (scan_center[1] - point[1]) ** 2

    return d <= scanner_radius ** 2

def load_bounds(mpq):
    # See the link for more information
    # http://www.galaxywiki.net/MapInfo_(File_Format)

    data = mpq.read_file("MapInfo")
    #f = open("MapInfo", "wb")
    #f.write(bytes(data))
    #f.close()
    data = StringIO(data)

    version = load_int(data, 0x04)

    #print "version = {}".format(hex(version))
    
    
    if version < 0x17 or version > 0x20:
        raise Exception("Unsupported s2ma/MapInfo version: {}".format(hex(version)))

    if 0x18 <= version and version <= 0x20:
        width = load_int(data, 0x10)
        height = load_int(data, 0x14)
    elif version == 0x17:
        width = load_int(data, 0x08)
        height = load_int(data, 0x0c)
    
    i = 0
    if version == 0x17:
        i = 0x21
    elif version == 0x18 or version == 0x19:
        i = 0x24
    else:
        i = 0x29

    fog = load_string(data, i)
    texture = load_string(data)

    #print width, height, fog, texture

    camera = tuple(load_int(data) for i in range(4))
    if version == 0x20:
        camera = (camera[0], camera[1], camera[2], camera[3])
    else:
        camera = (camera[0], camera[1], camera[2], camera[3])

    #print camera
    
    return width, height, camera

def load_int(data, start=None):
    if not (start is None):
        data.seek(start)
    return sum(ord(data.read(1)) << 8*i for i in range(4))
def load_string(data, start=None):
    if not (start is None):
        data.seek(start)
    s = ""
    while True:
        b = data.read(1)
        if len(b) == 0:
            return s
        if ord(b) == 0x00:
            return s
        s += b

class Translation():
    def __init__(self, map_bounds, minimap_size):
        self.map_bounds = (0, 0) + tuple(map_bounds[0:2])
        self.playable_size = (map_bounds[2][2] - map_bounds[2][0], 
                              map_bounds[2][3] - map_bounds[2][1])
        self.minimap = minimap_size
        self.camera = map_bounds[2]
        self.bl = tuple(self.camera[0:2])
        self.tr = tuple(self.camera[2:4])
    
        self.scale = (self.playable_size[0] / float(minimap_size[0]),
                      self.playable_size[1] / float(minimap_size[1]))

        #print "Translation __init__"
        #print "Scale {}".format(self.scale)

    def mini2map(self, x, y=None):
        if y is None:
            (x, y) = x

        newx = x * self.scale[0] + self.camera[0]
        newy = (self.minimap[1] - y) * self.scale[1] + self.camera[1]
    
        return (newx, newy)
            
    def map2mini(self, x, y=None):
        if y is None:
            (x, y) = x

        newx = (x - self.camera[0]) / self.scale[0]
        newy = self.minimap[1] - (y - self.camera[1]) / self.scale[1]
        
        return (newx, newy)

    def box_map2mini(self, box):
        
        bl = self.map2mini(box[0], box[1])
        tr = self.map2mini(box[2], box[3])
        
        # Flip the y-values. 
        bl, tr = ((bl[0], tr[1]), (tr[0], bl[1]))
        
        return bl+tr

if __name__ == "__main__":
    main(parse_args(sys.argv[1:]))
