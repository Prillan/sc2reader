# -*- coding: utf-8 -*-
"""
  Script for finding out scouting patterns for overlords and scans.

  Requires 
  - sc2reader (github.com/GraylinKim/sc2reader)
  - pil (www.pythonware.com/products/pil/)
"""

import argparse
from datetime import datetime
import hashlib
from PIL import Image, ImageDraw
import os
import cPickle as pickle
import pprint
import sc2reader
from sc2reader.events import *
from sc2reader.objects import *
from StringIO import StringIO
import sys

# (y_offset, w, h)
minimap_data = { "Cloud Kingdom LE": (256-194, 127, 194-62) }
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
    parser.add_argument("--heatmap-points", default=100, metavar="N", type=int,
        help="The number of points to use on the heatmap. This specifies that N*N points will be used in a grid")
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

    for hash in data:
        image = load_minimap(data[hash]["map"], data[hash]["minimap"])
        trans = Translation(minimap_data[data[hash]["map"]][1:], data[hash]["bounds"])
        if args.heatmap:
            create_scan_heatmap(image, trans, data[hash]["terran"], 
                                steps=args.heatmap_points, 
                                point_radius=1).show()
        draw_scans(image, trans, data[hash]["terran"])

        #test_drawing(image)
        #image.show()
        # log("Trying load")
        # image.load()
        # log("Trying save")
        # image.save("out.tga")
        image.show()

def do_stuff(args):
    replays = sc2reader.load_replays(args.FILES, options={"load_map":True, "debug":True})
    
    data = {}
    for replay in replays:
        log("New replay")

        terrans = [{'player': p, 'selected': None, 'scans': []} for p in replay.players if p.play_race == "Terran"]
        zergs = [{'player': p, 'selected': None} for p in replay.players if p.play_race == "Zerg"]
                
        for event in replay.events:
            if args.seconds != 0 and event.time.total_seconds() > args.seconds:
                break  

            for t in terrans:
                if t["player"].pid != event.pid:
                    continue
                if isinstance(event, SelectionEvent):

                    t["selected"] = event.objects
                elif isinstance(event, LocationAbilityEvent):

                    if event.ability_code == 0x1060:
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


def load_minimap(mapname, tgadata):
    image = Image.open(StringIO(tgadata))

    data = minimap_data[mapname]

    return image.crop((0, data[0], data[1], data[0]+data[2])) 

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

def create_scan_heatmap(image, translation, scans, steps=10, 
                        offsets=(2, 2), copy=True, point_radius=1):
    # Se how many times each point is hit by a scan
    # The points is a steps*steps grid

    map_size = translation.playable_size

    stepx = float(map_size[0] - 2*offsets[0]) / (steps - 1)
    stepy = float(map_size[1] - 2*offsets[1]) / (steps - 1)
    
    points = [[(offsets[0] + col*stepx, offsets[1] + row*stepy), 0]
              for col in range(steps) for row in range(steps)]

    for scan in scans:
        for point in points:
            if inside(point[0], (scan[1], scan[2])):
                point[1] += 1

    
    # Normalize
    maximum = max(p[1] for p in points)
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
        
        pos2 = translation.map2mini(pos)
        r2 = 0.5

        # draw.ellipse((pos2[0] - (point_radius + r2), pos2[1] - (point_radius + r2),
        #               pos2[0] + point_radius + r2, pos2[1] + point_radius + r2), 
        #              fill="black")

        if color is None:
            continue
        
        if point_radius <= 1:
            draw.point(pos2, fill=color)
        else:
            draw.ellipse((pos2[0] - point_radius, pos2[1] - point_radius,
                          pos2[0] + point_radius, pos2[1] + point_radius), 
                         fill=color)
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
    
    width = load_int(data, 0x10)
    height = load_int(data, 0x14)
    
    i = 0x29
    byte = 0
    
    firstPart = True

    # Two strings follow the initial bytes, find them
    while True:
        byte = data[i]
        if ord(byte) == 0:
            i += 1
            if not firstPart:
                break
            firstPart = False
        i += 1

    camera = tuple(load_int(data, i + j * 4) for j in range(4))
    camera = (camera[0] + 7, camera[1] + 4, camera[2] - 7, camera[3] - 4)

    return width, height, camera

def load_int(data, start):
    return sum(ord(data[start + i]) << 8*i for i in range(4))

class Translation():
    def __init__(self, minimap, map_bounds):
        self.minimap = minimap
        self.playable_size = tuple(map_bounds[0:2])
        self.camera = map_bounds[2]

        self.scaleX = float(minimap[0]) / self.playable_size[0]
        self.scaleY = float(minimap[1]) / self.playable_size[1]
    
    def mini2map(self, x, y=None):
        if y is None:
            (x, y) = x

        newx = x / self.scaleX
        newy = self.map[1] - (y / self.scaleY)

        newx = newx + self.camera[0]
        newy = newy + self.camera[1]
    
        return (newx, newy)
            
    def map2mini(self, x, y=None):
        if y is None:
            (x, y) = x

        # TODO: This needs to be tested by scanning all the corners
        #       of at least 2 maps
            
        newx = x# - self.camera[0]
        newy = y# - self.camera[1]

        newx = newx * self.scaleX
        newy = (self.playable_size[1] - newy) * self.scaleY

        return (newx, newy)

    def box_map2mini(self, box):
        
        bl = self.map2mini(box[0], box[1])
        tr = self.map2mini(box[2], box[3])
        
        # Flip the y-values. 
        bl, tr = ((bl[0], tr[1]), (tr[0], bl[1]))
        
        return bl+tr

if __name__ == "__main__":
    main(parse_args(sys.argv[1:]))
