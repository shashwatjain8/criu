from __future__ import print_function
import argparse
import sys
import json
import os

import pycriu
from struct import *
import random

PAGE_SIZE = 0x1000
DWORD_SIZE = 4
QWORD_SIZE = 8


def inf(opts):
    if opts['in']:
        return open(opts['in'], 'rb')
    else:
        if (sys.version_info < (3, 0)):
            return sys.stdin
        if sys.stdin.isatty():
            # If we are reading from a terminal (not a pipe) we want text input and not binary
            return sys.stdin
        return sys.stdin.buffer


def outf(opts, decode):
    # Decode means from protobuf to JSON.
    # Use text when writing to JSON else use binaray mode
    if opts['out']:
        mode = 'wb+'
        if decode:
            mode = 'w+'
        return open(opts['out'], mode)
    else:
        if (sys.version_info < (3, 0)):
            return sys.stdout
        if decode:
            return sys.stdout
        return sys.stdout.buffer


def dinf(opts, name):
    return open(os.path.join(opts['dir'], name), mode='rb')


# The function for now involves some partial hardcoding with respect to number of variables adn their sizes. 
# This can be removed by putting code to understand binary code 

def modify(opts):
    # Load All requried Images to locate stack and modify pages.img
    pid = opts['in']
    try:
        # Load PageMap Image
        opts['in'] = opts['dir'] + "/pagemap-" + pid + ".img"
        pageimg = pycriu.images.load(inf(opts), True, opts['nopl'])
        # Load MMap Image
        opts['in'] = opts['dir'] + "/mm-" + pid + ".img"
        memimg = pycriu.images.load(inf(opts), True, opts['nopl'])
        # Load Core Image
        opts['in'] = opts['dir'] + "/core-" + pid + ".img"
        coreimg = pycriu.images.load(inf(opts), True, opts['nopl'])

    except pycriu.images.MagicException as exc:
        print("Unknown magic %#x.\n"\
          "Maybe you are feeding me an image with "\
          "raw data(i.e. pages.img)?" % exc.magic, file=sys.stderr)
        sys.exit(1)

    indent = 4
    # Images Loaded Successfully. Look for Stack Location for Modification of Variables
    # Load Stack and Base Frame Pointers from Core File
    base_pointer = coreimg['entries'][0]['thread_info']['gpregs']['bp']
    stack_pointer = coreimg['entries'][0]['thread_info']['gpregs']['sp']
    page = 0

    # Search for VMA which Holds the Stack
    vmas = memimg['entries'][0]['vmas']
    while page < len(vmas):
        if "MAP_GROWSDOWN" in vmas[page]['flags']:
            break; 
        page = page + 1
    start_stack_vma = vmas[page]['start'] 
    end_stack_vma = vmas[page]['end'] 
    
    # Load the Page Mapping information to get Stack Data from pages.img
    total_pages = 0
    page_entries = pageimg['entries']
    stack_area_page = 0
    stack_area_offset = ''
    num_pages_for_stack = 0
    for entry in page_entries:
        try:
            if start_stack_vma <= entry['vaddr'] and end_stack_vma > entry['vaddr']:
                stack_area_page = total_pages
                stack_area_offset =  entry['vaddr']
                num_pages_for_stack = entry['nr_pages']
            total_pages += entry['nr_pages']
        except:
            continue
    
    # Read the pages.img and modify locals
    pages = open(opts['dir'] + '/pages-1.img', 'r+b')
    # Seek Till Base Pointer
    # Hardcoded 0x20 for 4 passed by reference addresses in the callee function for target process for now. 
    # Need to use a binary code lifter to automate finding of variables
    pages.seek((PAGE_SIZE * stack_area_page) + (int(base_pointer,16) - int(stack_area_offset,16)) - 0x20,0)
    x = pages.read(QWORD_SIZE)
    v1l = hex(int.from_bytes(x, byteorder='little'))
    x = pages.read(QWORD_SIZE)
    v2l = hex(int.from_bytes(x, byteorder='little'))
    x = pages.read(QWORD_SIZE)
    v3l = hex(int.from_bytes(x, byteorder='little'))
    x = pages.read(QWORD_SIZE)
    v4l = hex(int.from_bytes(x, byteorder='little'))

    # Generate Random Values for the elapsed variables and Strings and Modidy in the Stack
    # Vxl variables hold addresses for variables as gotten from Base Pointer Relative Offsets.

    pages.seek((PAGE_SIZE * stack_area_page) + (int(v4l,16) - int(stack_area_offset,16)),0)
    x = pages.read(DWORD_SIZE)
    v4v = int(hex(int.from_bytes(x, byteorder='little')),16)
    ran = random.randint(v4v,40)
    pages.seek((PAGE_SIZE * stack_area_page) + (int(v4l,16) - int(stack_area_offset,16)),0)
    x = ran.to_bytes(4, 'little')
    pages.write(x)

    ran -= 1

    pages.seek((PAGE_SIZE * stack_area_page) + (int(v3l,16) - int(stack_area_offset,16)),0)
    x = pages.read(DWORD_SIZE)
    v3v = int(hex(int.from_bytes(x, byteorder='little')),16)
    pages.seek((PAGE_SIZE * stack_area_page) + (int(v3l,16) - int(stack_area_offset,16)),0)
    x = ran.to_bytes(4, 'little')
    pages.write(x)
    
    pages.seek((PAGE_SIZE * stack_area_page) + (int(v2l,16) - int(stack_area_offset,16)),0)
    x = pages.read(2*QWORD_SIZE)
    strx = x.decode('utf-8')
    strrand = (''.join(random.sample(strx,len(strx)))).encode()
    pages.seek((PAGE_SIZE * stack_area_page) + (int(v2l,16) - int(stack_area_offset,16)),0)
    pages.write(strrand)

    pages.seek((PAGE_SIZE * stack_area_page) + (int(v1l,16) - int(stack_area_offset,16)),0)
    x = pages.read(2*QWORD_SIZE)
    #v1v = hex(int.from_bytes(x, byteorder='little'))
    strx = x.decode('utf-8')
    strrand = (''.join(random.sample(strx,len(strx)))).encode()
    pages.seek((PAGE_SIZE * stack_area_page) + (int(v1l,16) - int(stack_area_offset,16)),0)
    pages.write(strrand)

    pages.close()

    return 0


def decode(opts):
    indent = None

    try:
        img = pycriu.images.load(inf(opts), opts['pretty'], opts['nopl'])
    except pycriu.images.MagicException as exc:
        print("Unknown magic %#x.\n"\
          "Maybe you are feeding me an image with "\
          "raw data(i.e. pages.img)?" % exc.magic, file=sys.stderr)
        sys.exit(1)

    if opts['pretty']:
        indent = 4

    f = outf(opts, True)
    json.dump(img, f, indent=indent)
    if f == sys.stdout:
        f.write("\n")


def encode(opts):
    try:
        img = json.load(inf(opts))
    except UnicodeDecodeError:
        print("Cannot read JSON.\n"\
          "Maybe you are feeding me an image with protobuf data? "\
          "Encode expects JSON input.", file=sys.stderr)
        sys.exit(1)
    pycriu.images.dump(img, outf(opts, False))


def info(opts):
    infs = pycriu.images.info(inf(opts))
    json.dump(infs, sys.stdout, indent=4)
    print()


def get_task_id(p, val):
    return p[val] if val in p else p['ns_' + val][0]


#
# Explorers
#


class ps_item:
    def __init__(self, p, core):
        self.pid = get_task_id(p, 'pid')
        self.ppid = p['ppid']
        self.p = p
        self.core = core
        self.kids = []


def show_ps(p, opts, depth=0):
    print("%7d%7d%7d   %s%s" %
          (p.pid, get_task_id(p.p, 'pgid'), get_task_id(p.p, 'sid'), ' ' *
           (4 * depth), p.core['tc']['comm']))
    for kid in p.kids:
        show_ps(kid, opts, depth + 1)


def explore_ps(opts):
    pss = {}
    ps_img = pycriu.images.load(dinf(opts, 'pstree.img'))
    for p in ps_img['entries']:
        core = pycriu.images.load(
            dinf(opts, 'core-%d.img' % get_task_id(p, 'pid')))
        ps = ps_item(p, core['entries'][0])
        pss[ps.pid] = ps

    # Build tree
    psr = None
    for pid in pss:
        p = pss[pid]
        if p.ppid == 0:
            psr = p
            continue

        pp = pss[p.ppid]
        pp.kids.append(p)

    print("%7s%7s%7s   %s" % ('PID', 'PGID', 'SID', 'COMM'))
    show_ps(psr, opts)


files_img = None


def ftype_find_in_files(opts, ft, fid):
    global files_img

    if files_img is None:
        try:
            files_img = pycriu.images.load(dinf(opts, "files.img"))['entries']
        except:
            files_img = []

    if len(files_img) == 0:
        return None

    for f in files_img:
        if f['id'] == fid:
            return f

    return None


def ftype_find_in_image(opts, ft, fid, img):
    f = ftype_find_in_files(opts, ft, fid)
    if f:
        return f[ft['field']]

    if ft['img'] is None:
        ft['img'] = pycriu.images.load(dinf(opts, img))['entries']
    for f in ft['img']:
        if f['id'] == fid:
            return f
    return None


def ftype_reg(opts, ft, fid):
    rf = ftype_find_in_image(opts, ft, fid, 'reg-files.img')
    return rf and rf['name'] or 'unknown path'


def ftype_pipe(opts, ft, fid):
    p = ftype_find_in_image(opts, ft, fid, 'pipes.img')
    return p and 'pipe[%d]' % p['pipe_id'] or 'pipe[?]'


def ftype_unix(opts, ft, fid):
    ux = ftype_find_in_image(opts, ft, fid, 'unixsk.img')
    if not ux:
        return 'unix[?]'

    n = ux['name'] and ' %s' % ux['name'] or ''
    return 'unix[%d (%d)%s]' % (ux['ino'], ux['peer'], n)


file_types = {
    'REG': {
        'get': ftype_reg,
        'img': None,
        'field': 'reg'
    },
    'PIPE': {
        'get': ftype_pipe,
        'img': None,
        'field': 'pipe'
    },
    'UNIXSK': {
        'get': ftype_unix,
        'img': None,
        'field': 'usk'
    },
}


def ftype_gen(opts, ft, fid):
    return '%s.%d' % (ft['typ'], fid)


files_cache = {}


def get_file_str(opts, fd):
    key = (fd['type'], fd['id'])
    f = files_cache.get(key, None)
    if not f:
        ft = file_types.get(fd['type'], {'get': ftype_gen, 'typ': fd['type']})
        f = ft['get'](opts, ft, fd['id'])
        files_cache[key] = f

    return f


def explore_fds(opts):
    ps_img = pycriu.images.load(dinf(opts, 'pstree.img'))
    for p in ps_img['entries']:
        pid = get_task_id(p, 'pid')
        idi = pycriu.images.load(dinf(opts, 'ids-%s.img' % pid))
        fdt = idi['entries'][0]['files_id']
        fdi = pycriu.images.load(dinf(opts, 'fdinfo-%d.img' % fdt))

        print("%d" % pid)
        for fd in fdi['entries']:
            print("\t%7d: %s" % (fd['fd'], get_file_str(opts, fd)))

        fdi = pycriu.images.load(dinf(opts, 'fs-%d.img' % pid))['entries'][0]
        print("\t%7s: %s" %
              ('cwd', get_file_str(opts, {
                  'type': 'REG',
                  'id': fdi['cwd_id']
              })))
        print("\t%7s: %s" %
              ('root', get_file_str(opts, {
                  'type': 'REG',
                  'id': fdi['root_id']
              })))


class vma_id:
    def __init__(self):
        self.__ids = {}
        self.__last = 1

    def get(self, iid):
        ret = self.__ids.get(iid, None)
        if not ret:
            ret = self.__last
            self.__last += 1
            self.__ids[iid] = ret

        return ret


def explore_mems(opts):
    ps_img = pycriu.images.load(dinf(opts, 'pstree.img'))
    vids = vma_id()
    for p in ps_img['entries']:
        pid = get_task_id(p, 'pid')
        mmi = pycriu.images.load(dinf(opts, 'mm-%d.img' % pid))['entries'][0]

        print("%d" % pid)
        print("\t%-36s    %s" % ('exe',
                                 get_file_str(opts, {
                                     'type': 'REG',
                                     'id': mmi['exe_file_id']
                                 })))

        for vma in mmi['vmas']:
            st = vma['status']
            if st & (1 << 10):
                fn = ' ' + 'ips[%lx]' % vids.get(vma['shmid'])
            elif st & (1 << 8):
                fn = ' ' + 'shmem[%lx]' % vids.get(vma['shmid'])
            elif st & (1 << 11):
                fn = ' ' + 'packet[%lx]' % vids.get(vma['shmid'])
            elif st & ((1 << 6) | (1 << 7)):
                fn = ' ' + get_file_str(opts, {
                    'type': 'REG',
                    'id': vma['shmid']
                })
                if vma['pgoff']:
                    fn += ' + %#lx' % vma['pgoff']
                if st & (1 << 7):
                    fn += ' (s)'
            elif st & (1 << 1):
                fn = ' [stack]'
            elif st & (1 << 2):
                fn = ' [vsyscall]'
            elif st & (1 << 3):
                fn = ' [vdso]'
            elif vma['flags'] & 0x0100:  # growsdown
                fn = ' [stack?]'
            else:
                fn = ''

            if not st & (1 << 0):
                fn += ' *'

            prot = vma['prot'] & 0x1 and 'r' or '-'
            prot += vma['prot'] & 0x2 and 'w' or '-'
            prot += vma['prot'] & 0x4 and 'x' or '-'

            astr = '%08lx-%08lx' % (vma['start'], vma['end'])
            print("\t%-36s%s%s" % (astr, prot, fn))


def explore_rss(opts):
    ps_img = pycriu.images.load(dinf(opts, 'pstree.img'))
    for p in ps_img['entries']:
        pid = get_task_id(p, 'pid')
        vmas = pycriu.images.load(dinf(opts, 'mm-%d.img' %
                                       pid))['entries'][0]['vmas']
        pms = pycriu.images.load(dinf(opts, 'pagemap-%d.img' % pid))['entries']

        print("%d" % pid)
        vmi = 0
        pvmi = -1
        for pm in pms[1:]:
            pstr = '\t%lx / %-8d' % (pm['vaddr'], pm['nr_pages'])
            while vmas[vmi]['end'] <= pm['vaddr']:
                vmi += 1

            pme = pm['vaddr'] + (pm['nr_pages'] << 12)
            vstr = ''
            while vmas[vmi]['start'] < pme:
                vma = vmas[vmi]
                if vmi == pvmi:
                    vstr += ' ~'
                else:
                    vstr += ' %08lx / %-8d' % (
                        vma['start'], (vma['end'] - vma['start']) >> 12)
                    if vma['status'] & ((1 << 6) | (1 << 7)):
                        vstr += ' ' + get_file_str(opts, {
                            'type': 'REG',
                            'id': vma['shmid']
                        })
                    pvmi = vmi
                vstr += '\n\t%23s' % ''
                vmi += 1

            vmi -= 1

            print('%-24s%s' % (pstr, vstr))


explorers = {
    'ps': explore_ps,
    'fds': explore_fds,
    'mems': explore_mems,
    'rss': explore_rss
}


def explore(opts):
    explorers[opts['what']](opts)


def main():
    desc = 'CRiu Image Tool'
    parser = argparse.ArgumentParser(
        description=desc, formatter_class=argparse.RawTextHelpFormatter)

    subparsers = parser.add_subparsers(
        help='Use crit CMD --help for command-specific help')

    # Decode
    decode_parser = subparsers.add_parser(
        'decode', help='convert criu image from binary type to json')
    decode_parser.add_argument(
        '--pretty',
        help=
        'Multiline with indents and some numerical fields in field-specific format',
        action='store_true')
    decode_parser.add_argument(
        '-i',
        '--in',
        help='criu image in binary format to be decoded (stdin by default)')
    decode_parser.add_argument(
        '-o',
        '--out',
        help='where to put criu image in json format (stdout by default)')
    decode_parser.set_defaults(func=decode, nopl=False)

    # Encode
    encode_parser = subparsers.add_parser(
        'encode', help='convert criu image from json type to binary')
    encode_parser.add_argument(
        '-i',
        '--in',
        help='criu image in json format to be encoded (stdin by default)')
    encode_parser.add_argument(
        '-o',
        '--out',
        help='where to put criu image in binary format (stdout by default)')
    encode_parser.set_defaults(func=encode)

    # Modify
    modify_parser = subparsers.add_parser(
        'modify', help='convert and modify criu image')
    modify_parser.add_argument(
        '-i',
        '--in',
        help='criu image in binary format to be decoded (stdin by default)')
    modify_parser.add_argument(
        '-o',
        '--out',
        help='where to put criu image in json format (stdout by default)')
    modify_parser.add_argument(
        '-d',
        '--dir',
        help='Dir for Dump Images')
    modify_parser.set_defaults(func=modify, nopl=False)
    

    # Info
    info_parser = subparsers.add_parser('info', help='show info about image')
    info_parser.add_argument("in")
    info_parser.set_defaults(func=info)

    # Explore
    x_parser = subparsers.add_parser('x', help='explore image dir')
    x_parser.add_argument('dir')
    x_parser.add_argument('what', choices=['ps', 'fds', 'mems', 'rss'])
    x_parser.set_defaults(func=explore)

    # Show
    show_parser = subparsers.add_parser(
        'show', help="convert criu image from binary to human-readable json")
    show_parser.add_argument("in")
    show_parser.add_argument('--nopl',
                             help='do not show entry payload (if exists)',
                             action='store_true')
    show_parser.set_defaults(func=decode, pretty=True, out=None)

    opts = vars(parser.parse_args())

    if not opts:
        sys.stderr.write(parser.format_usage())
        sys.stderr.write("crit: error: too few arguments\n")
        sys.exit(1)

    opts["func"](opts)


if __name__ == '__main__':
    main()
