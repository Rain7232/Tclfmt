#!/usr/bin/python
# -*- coding: utf-8 -*-

import sublime
import sublime_plugin
import os
import io

gEmpty = 0
curFile = ""
gIndentSize = 4
gIndent = 0
gWrapLines = []

gStoreLines = {
    "set": [],
    "pkg": [],
    "cfg": [],
    "key": [],
}

gFormatBaseIndex = {
    "set": 1,
    "pkg": 2,
    "cfg": 2,
    "key": 0,
}


class LineAttr:
    def __init__(self):
        self.empty = 0
        self.set = 0
        self.blockStart = 0
        self.blockMid = 0
        self.blockEnd = 0
        self.wrap = 0
        self.package = 0
        self.comment = 0
        self.structCfg = 0
        self.switch = 0
        self.switchKey = 0


def lineTrim(line):
    newLine = line.strip()
    if len(newLine) != 0 and newLine[0] == "#":
        # No change for the comment line
        return newLine
    else:
        words = newLine.split()
        newLine = " ".join(words)
        return newLine


def paddingGen(cnt):
    result = ""
    for _ in range(cnt):
        result += " " 
    return result


def blockInfoGet(lines):
    lblock = 0
    rblock = 0
    lbracket = 0
    rbracket = 0
    for _, line in enumerate(lines):
        lblock += line.count("{")
        rblock += line.count("}")
        lbracket += line.count("[")
        rbracket += line.count("]")

    return lblock, rblock, lbracket,rbracket


def wrapLinesStatus(lines):
    warpLineStatus = ""
    firstLine = lines[0]
    if firstLine[0] == "#" and firstLine[-1] == "\\":
        return warpLineStatus

    lblock, rblock, lbracket,rbracket = blockInfoGet(lines)
    if lblock > rblock:
        warpLineStatus = "blockStart"
    elif lblock < rblock:
        warpLineStatus = "blockEnd"
    elif lbracket > rbracket:
        warpLineStatus = "bracketStart"
    elif lbracket < rbracket:
        warpLineStatus = "bracketEnd"

    return warpLineStatus


def wrapLinesReformat():
    # Reformat
    formattedLines = []
    maxWordsLen = 0
    maxLen0 = 0
    maxLen1 = 0
    maxLenOther = 0

    for i, line in enumerate(gWrapLines):
        words = line.split()        
        if i == 0 or len(words) < 2:
            continue

        if maxWordsLen < len(words):
            maxWordsLen = len(words)
        if maxLen0 < len(words[0]):
            maxLen0 = len(words[0])
        if maxLen1 < len(words[1]) and len(words) > 2:
            maxLen1 = len(words[1])
        if maxLenOther < len(line):
            maxLenOther = len(line)

    maxLenOther2 = 0
    for i, line in enumerate(gWrapLines):
        words = line.split()
        if i == 0:
            # No change
            formattedLines.append(line)
        else:
            newLine = ""
            pad0 = 0
            pad1 = 0
            padding = paddingGen(gIndentSize)
            if maxWordsLen > 3 or "expr " in line:
                # It's hard to align these lines, so skip formatting
                surPadding = paddingGen(maxLenOther - len(line))
                newLine = line.replace("\\", surPadding+"\\")
                newLine = "%s%s" % (padding, newLine)
            elif len(words) == 1:
                if len(line) == 1 and line[0] == "]":
                    padding = ""
                newLine = "%s%s" % (padding, line)
            else:
                pad0 = paddingGen(maxLen0-len(words[0]))
                pad1 = paddingGen(maxLen1-len(words[1]))
                rest = " ".join(words[2:])
                newLine = "%s%s %s%s%s %s" % (padding, words[0], pad0, words[1], pad1, rest)
                newLine = newLine.rstrip()

            formattedLines.append(newLine)
            if maxLenOther2 < len(newLine):
                maxLenOther2 = len(newLine)

    # Align the first line with others
    if abs(maxLenOther2 - len(formattedLines[0])) < 10 :
        maxLen = maxLenOther2 if maxLenOther2 > len(formattedLines[0]) else len(formattedLines[0])
        for i, line in enumerate(formattedLines):
            if line[-1] == "\\":
                surPadding = paddingGen(maxLen - len(line))
                formattedLines[i] = line.replace("\\", surPadding+"\\")

    gWrapLines.clear()
    return formattedLines


def linesReformat(storeLines, index):
    formattedLines = []
    maxLen = 0
    for line in storeLines:
        words = line.split()
        if maxLen < len(words[index]):
            maxLen = len(words[index])

    for line in storeLines:
        words = line.split()
        padding = paddingGen(maxLen-len(words[index]))
        prefix = " ".join(words[:index+1])
        surfix = " ".join(words[index+1:])
        newLine = "%s%s %s" % (prefix, padding, surfix)
        formattedLines.append(newLine)

    return formattedLines


def prePopWraps(f, padding):
    if len(gWrapLines) != 0:
        newLines = wrapLinesReformat()
        for line in newLines:
            f.write("%s%s\n" % (padding, line))
    return


def storedLinesPopOthers(f, exclude):
    for key in gStoreLines:
        if key == exclude:
            continue
        else:
            storedLinesPop(f,key)


def storedLinesPop(f, key):
    global gStoreLines
    index = gFormatBaseIndex[key]
    padding = paddingGen(gIndent)
    if len(gStoreLines[key]) != 0:
        newLines = linesReformat(gStoreLines[key], index)
        for line in newLines:
            f.write("%s%s\n" % (padding, line))

    gStoreLines[key].clear()
    return


def lineMark(line):
    global cur
    
    # cur = LineAttr()
    words = line.split()

    # For empty lines
    if len(line) == 0:
        cur.empty = 1
        return 

    # For comment lines
    if line[0] == "#" and line[-1] != "\\": 
        cur.comment = 1
        return

    # For reformating the Package Require
    if "package require" in line:
        cur.package = 1
        return

    # For reformating the single line SETs
    if line[0:4] == "set " and line[-1] != "\\" and line[-1] != "[":
        cur.set = 1
        return

    # For reformating the "configure -"
    if "configure -" in line and line.count("{") < line.count("}"): 
        cur.structCfg = 1
        return

    # For reformating the "xxxx -" in the SWITCH{}
    if len(words) == 2 and words[1] == "-":
        cur.switchKey = 1
        return

    # For marking the block
    if line[0] == "}" and line[-1] == "{":
        cur.blockMid = 1
    elif line.count("{") > line.count("}"):
        cur.blockStart = 1
        if "switch" in line:
            cur.switch = 1
    elif line.count("{") < line.count("}"):
        cur.blockEnd = 1
   
    # For Multilines starting with [
    if line[-1] == ("["):
        cur.blockStart = 1

    if line[-1] == ("]") and len(line) == 1:
        cur.blockEnd = 1

    # For Multilines starting with \
    if line[-1] == "\\":
        cur.wrap = 1


def linePrint(f,line):
    global cur, pre, gEmpty, gIndent, gStoreLines
    
    padding = paddingGen(gIndent)
    
    # Reformat the empty lines
    if cur.empty == 1:
        gEmpty += 1
        if gEmpty != 1:
            return
    else:
        # Print the line at the end
        gEmpty = 0

    # Reformat the stored lines, then print them out.
    key = ""
    if cur.set == 1 :
        key = "set"
    elif cur.package == 1:
        key = "pkg"
    elif cur.switchKey == 1:
        key = "key"
    elif cur.structCfg == 1:
        key = "cfg"
    else:
        key = "all"

    storedLinesPopOthers(f, key)
    if key != "all":
        gStoreLines[key].append(line)
        return

    # Reformat the multilines with \, then print them out.
    if cur.wrap == 1:
        gWrapLines.append(line)
        return
    elif pre.wrap == 1 and cur.wrap == 0:
        # Handle the last line
        gWrapLines.append(line)
        status = wrapLinesStatus(gWrapLines)
        prePopWraps(f, padding)
        if status == "blockEnd" or status == "bracketEnd":
            gIndent -= gIndentSize
        elif status == "blockStart" or status == "bracketStart":
            gIndent += gIndentSize
        return
    
    # Recalculate the padding
    if cur.blockStart == 1:
        f.write("%s%s\n" % (padding,line))
        gIndent += gIndentSize
    elif cur.blockMid == 1:
        gIndent -= gIndentSize
        padding = paddingGen(gIndent)
        f.write("%s%s\n" % (padding,line))
        gIndent += gIndentSize
    elif cur.blockEnd == 1:
        gIndent -= gIndentSize
        padding = paddingGen(gIndent)
        f.write("%s%s\n" % (padding,line))
    else:        
        if len(line) == 0:
            f.write("\n")
        else:
            padding = paddingGen(gIndent)
            f.write("%s%s\n" % (padding,line))


def tclfmtRun():
    global cur, pre, curFile, gEmpty, gIndent, gStoreLines

    gEmpty = 0
    gIndent = 0
    cur = LineAttr()
    pre = LineAttr()
    gStoreLines = {
        "set": [],
        "pkg": [],
        "cfg": [],
        "key": [],
    }

    target = curFile
    saveto = settings.get("save_to")
    if saveto != "":
        path = os.path.dirname(curFile)
        target = path+"/"+saveto

    with io.StringIO() as output:
        # Open current file for reading
        with io.open(curFile, mode="r", encoding="utf-8") as rFid:
            for line in rFid:
                line = lineTrim(line)
                lineMark(line)
                linePrint(output, line)
                pre = cur
                cur = LineAttr()

        # Write the formatted lines back
        with io.open(target, mode='w', encoding="utf-8") as wFid:
            wFid.write(output.getvalue())


# For Sublime plugin
settings = None
def plugin_loaded():
    global settings
    settings = sublime.load_settings('Tclfmt.sublime-settings')

def isTclSource(view):
    # Return True if the given view contains TCL source code.
    return view.score_selector(0, 'source.tcl') != 0

# Sublime 
class TclfmtCommand(sublime_plugin.TextCommand):
    def is_enabled(self):
        return isTclSource(self.view)

    def run(self, edit):
        tclfmtRun()

class TclfmtListener(sublime_plugin.EventListener):
    def on_pre_save(self, view):
        if not settings.get('format_on_save', True):
            return
        sublime.set_timeout(lambda: view.run_command("tclfmt"), 0)

    def on_activated(self, view):
        global curFile
        curFile = view.file_name()
