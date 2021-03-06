#!/usr/bin/env python
#
# Copyright 2011-2013 The Rust Project Developers. See the COPYRIGHT
# file at the top-level directory of this distribution and at
# http://rust-lang.org/COPYRIGHT.
#
# Licensed under the Apache License, Version 2.0 <LICENSE-APACHE or
# http://www.apache.org/licenses/LICENSE-2.0> or the MIT license
# <LICENSE-MIT or http://opensource.org/licenses/MIT>, at your
# option. This file may not be copied, modified, or distributed
# except according to those terms.

# This script uses the following Unicode tables:
# - DerivedCoreProperties.txt
# - DerivedNormalizationProps.txt
# - EastAsianWidth.txt
# - auxiliary/GraphemeBreakProperty.txt
# - PropList.txt
# - ReadMe.txt
# - Scripts.txt
# - UnicodeData.txt
#
# Since this should not require frequent updates, we just store this
# out-of-line and check the unicode.rs file into git.

import fileinput, re, os, sys, operator

bytes_old = 0
bytes_new = 0

preamble = '''// Copyright 2012-2016 The Rust Project Developers. See the COPYRIGHT
// file at the top-level directory of this distribution and at
// http://rust-lang.org/COPYRIGHT.
//
// Licensed under the Apache License, Version 2.0 <LICENSE-APACHE or
// http://www.apache.org/licenses/LICENSE-2.0> or the MIT license
// <LICENSE-MIT or http://opensource.org/licenses/MIT>, at your
// option. This file may not be copied, modified, or distributed
// except according to those terms.

// NOTE: The following code was generated by "src/etc/unicode.py", do not edit directly

#![allow(missing_docs, non_upper_case_globals, non_snake_case)]
'''

# Mapping taken from Table 12 from:
# http://www.unicode.org/reports/tr44/#General_Category_Values
expanded_categories = {
    'Lu': ['LC', 'L'], 'Ll': ['LC', 'L'], 'Lt': ['LC', 'L'],
    'Lm': ['L'], 'Lo': ['L'],
    'Mn': ['M'], 'Mc': ['M'], 'Me': ['M'],
    'Nd': ['N'], 'Nl': ['N'], 'No': ['No'],
    'Pc': ['P'], 'Pd': ['P'], 'Ps': ['P'], 'Pe': ['P'],
    'Pi': ['P'], 'Pf': ['P'], 'Po': ['P'],
    'Sm': ['S'], 'Sc': ['S'], 'Sk': ['S'], 'So': ['S'],
    'Zs': ['Z'], 'Zl': ['Z'], 'Zp': ['Z'],
    'Cc': ['C'], 'Cf': ['C'], 'Cs': ['C'], 'Co': ['C'], 'Cn': ['C'],
}

# these are the surrogate codepoints, which are not valid rust characters
surrogate_codepoints = (0xd800, 0xdfff)

def fetch(f):
    if not os.path.exists(os.path.basename(f)):
        os.system("curl -O http://www.unicode.org/Public/UNIDATA/%s"
                  % f)

    if not os.path.exists(os.path.basename(f)):
        sys.stderr.write("cannot load %s" % f)
        exit(1)

def is_surrogate(n):
    return surrogate_codepoints[0] <= n <= surrogate_codepoints[1]

def load_unicode_data(f):
    fetch(f)
    gencats = {}
    to_lower = {}
    to_upper = {}
    to_title = {}
    combines = {}
    canon_decomp = {}
    compat_decomp = {}

    udict = {};
    range_start = -1;
    for line in fileinput.input(f):
        data = line.split(';');
        if len(data) != 15:
            continue
        cp = int(data[0], 16);
        if is_surrogate(cp):
            continue
        if range_start >= 0:
            for i in xrange(range_start, cp):
                udict[i] = data;
            range_start = -1;
        if data[1].endswith(", First>"):
            range_start = cp;
            continue;
        udict[cp] = data;

    for code in udict:
        [code_org, name, gencat, combine, bidi,
         decomp, deci, digit, num, mirror,
         old, iso, upcase, lowcase, titlecase ] = udict[code];

        # generate char to char direct common and simple conversions
        # uppercase to lowercase
        if lowcase != "" and code_org != lowcase:
            to_lower[code] = (int(lowcase, 16), 0, 0)

        # lowercase to uppercase
        if upcase != "" and code_org != upcase:
            to_upper[code] = (int(upcase, 16), 0, 0)

        # title case
        if titlecase.strip() != "" and code_org != titlecase:
            to_title[code] = (int(titlecase, 16), 0, 0)

        # store decomposition, if given
        if decomp != "":
            if decomp.startswith('<'):
                seq = []
                for i in decomp.split()[1:]:
                    seq.append(int(i, 16))
                compat_decomp[code] = seq
            else:
                seq = []
                for i in decomp.split():
                    seq.append(int(i, 16))
                canon_decomp[code] = seq

        # place letter in categories as appropriate
        for cat in [gencat, "Assigned"] + expanded_categories.get(gencat, []):
            if cat not in gencats:
                gencats[cat] = []
            gencats[cat].append(code)

        # record combining class, if any
        if combine != "0":
            if combine not in combines:
                combines[combine] = []
            combines[combine].append(code)

    # generate Not_Assigned from Assigned
    gencats["Cn"] = gen_unassigned(gencats["Assigned"])
    # Assigned is not a real category
    del(gencats["Assigned"])
    # Other contains Not_Assigned
    gencats["C"].extend(gencats["Cn"])
    gencats = group_cats(gencats)
    combines = to_combines(group_cats(combines))

    return (canon_decomp, compat_decomp, gencats, combines, to_upper, to_lower, to_title)

def load_special_casing(f, to_upper, to_lower, to_title):
    fetch(f)
    for line in fileinput.input(f):
        data = line.split('#')[0].split(';')
        if len(data) == 5:
            code, lower, title, upper, _comment = data
        elif len(data) == 6:
            code, lower, title, upper, condition, _comment = data
            if condition.strip():  # Only keep unconditional mappins
                continue
        else:
            continue
        code = code.strip()
        lower = lower.strip()
        title = title.strip()
        upper = upper.strip()
        key = int(code, 16)
        for (map_, values) in [(to_lower, lower), (to_upper, upper), (to_title, title)]:
            if values != code:
                values = [int(i, 16) for i in values.split()]
                for _ in range(len(values), 3):
                    values.append(0)
                assert len(values) == 3
                map_[key] = values

def group_cats(cats):
    cats_out = {}
    for cat in cats:
        cats_out[cat] = group_cat(cats[cat])
    return cats_out

def group_cat(cat):
    cat_out = []
    letters = sorted(set(cat))
    cur_start = letters.pop(0)
    cur_end = cur_start
    for letter in letters:
        assert letter > cur_end, \
            "cur_end: %s, letter: %s" % (hex(cur_end), hex(letter))
        if letter == cur_end + 1:
            cur_end = letter
        else:
            cat_out.append((cur_start, cur_end))
            cur_start = cur_end = letter
    cat_out.append((cur_start, cur_end))
    return cat_out

def ungroup_cat(cat):
    cat_out = []
    for (lo, hi) in cat:
        while lo <= hi:
            cat_out.append(lo)
            lo += 1
    return cat_out

def gen_unassigned(assigned):
    assigned = set(assigned)
    return ([i for i in range(0, 0xd800) if i not in assigned] +
            [i for i in range(0xe000, 0x110000) if i not in assigned])

def to_combines(combs):
    combs_out = []
    for comb in combs:
        for (lo, hi) in combs[comb]:
            combs_out.append((lo, hi, comb))
    combs_out.sort(key=lambda comb: comb[0])
    return combs_out

def format_table_content(f, content, indent):
    line = " "*indent
    first = True
    for chunk in content.split(","):
        if len(line) + len(chunk) < 98:
            if first:
                line += chunk
            else:
                line += ", " + chunk
            first = False
        else:
            f.write(line + ",\n")
            line = " "*indent + chunk
    f.write(line)

def load_properties(f, interestingprops):
    fetch(f)
    props = {}
    re1 = re.compile("^ *([0-9A-F]+) *; *(\w+)")
    re2 = re.compile("^ *([0-9A-F]+)\.\.([0-9A-F]+) *; *(\w+)")

    for line in fileinput.input(os.path.basename(f)):
        prop = None
        d_lo = 0
        d_hi = 0
        m = re1.match(line)
        if m:
            d_lo = m.group(1)
            d_hi = m.group(1)
            prop = m.group(2)
        else:
            m = re2.match(line)
            if m:
                d_lo = m.group(1)
                d_hi = m.group(2)
                prop = m.group(3)
            else:
                continue
        if interestingprops and prop not in interestingprops:
            continue
        d_lo = int(d_lo, 16)
        d_hi = int(d_hi, 16)
        if prop not in props:
            props[prop] = []
        props[prop].append((d_lo, d_hi))

    # optimize if possible
    for prop in props:
        props[prop] = group_cat(ungroup_cat(props[prop]))

    return props

def escape_char(c):
    return "'\\u{%x}'" % c if c != 0 else "'\\0'"

def emit_bsearch_range_table(f):
    f.write("""
fn bsearch_range_table(c: char, r: &'static [(char, char)]) -> bool {
    use core::cmp::Ordering::{Equal, Less, Greater};
    r.binary_search_by(|&(lo, hi)| {
         if c < lo {
             Greater
         } else if hi < c {
             Less
         } else {
             Equal
         }
     })
     .is_ok()
}\n
""")

def emit_table(f, name, t_data, t_type = "&'static [(char, char)]", is_pub=True,
        pfun=lambda x: "(%s,%s)" % (escape_char(x[0]), escape_char(x[1]))):
    pub_string = ""
    if is_pub:
        pub_string = "pub "
    f.write("    %sconst %s: %s = &[\n" % (pub_string, name, t_type))
    data = ""
    first = True
    for dat in t_data:
        if not first:
            data += ","
        first = False
        data += pfun(dat)
    format_table_content(f, data, 8)
    f.write("\n    ];\n\n")

def emit_trie_lookup_range_table(f):
    f.write("""

// BoolTrie is a trie for representing a set of Unicode codepoints. It is
// implemented with postfix compression (sharing of identical child nodes),
// which gives both compact size and fast lookup.
//
// The space of Unicode codepoints is divided into 3 subareas, each
// represented by a trie with different depth. In the first (0..0x800), there
// is no trie structure at all; each u64 entry corresponds to a bitvector
// effectively holding 64 bool values.
//
// In the second (0x800..0x10000), each child of the root node represents a
// 64-wide subrange, but instead of storing the full 64-bit value of the leaf,
// the trie stores an 8-bit index into a shared table of leaf values. This
// exploits the fact that in reasonable sets, many such leaves can be shared.
//
// In the third (0x10000..0x110000), each child of the root node represents a
// 4096-wide subrange, and the trie stores an 8-bit index into a 64-byte slice
// of a child tree. Each of these 64 bytes represents an index into the table
// of shared 64-bit leaf values. This exploits the sparse structure in the
// non-BMP range of most Unicode sets.
pub struct BoolTrie {
    // 0..0x800 (corresponding to 1 and 2 byte utf-8 sequences)
    r1: [u64; 32],   // leaves

    // 0x800..0x10000 (corresponding to 3 byte utf-8 sequences)
    r2: [u8; 992],      // first level
    r3: &'static [u64],  // leaves

    // 0x10000..0x110000 (corresponding to 4 byte utf-8 sequences)
    r4: [u8; 256],       // first level
    r5: &'static [u8],   // second level
    r6: &'static [u64],  // leaves
}

fn trie_range_leaf(c: usize, bitmap_chunk: u64) -> bool {
    ((bitmap_chunk >> (c & 63)) & 1) != 0
}

fn trie_lookup_range_table(c: char, r: &'static BoolTrie) -> bool {
    let c = c as usize;
    if c < 0x800 {
        trie_range_leaf(c, r.r1[c >> 6])
    } else if c < 0x10000 {
        let child = r.r2[(c >> 6) - 0x20];
        trie_range_leaf(c, r.r3[child as usize])
    } else {
        let child = r.r4[(c >> 12) - 0x10];
        let leaf = r.r5[((child as usize) << 6) + ((c >> 6) & 0x3f)];
        trie_range_leaf(c, r.r6[leaf as usize])
    }
}\n
""")

def compute_trie(rawdata, chunksize):
    root = []
    childmap = {}
    child_data = []
    for i in range(len(rawdata) / chunksize):
        data = rawdata[i * chunksize: (i + 1) * chunksize]
        child = '|'.join(map(str, data))
        if child not in childmap:
            childmap[child] = len(childmap)
            child_data.extend(data)
        root.append(childmap[child])
    return (root, child_data)

def emit_bool_trie(f, name, t_data, is_pub=True):
    global bytes_old, bytes_new
    bytes_old += 8 * len(t_data)
    CHUNK = 64
    rawdata = [False] * 0x110000;
    for (lo, hi) in t_data:
        for cp in range(lo, hi + 1):
            rawdata[cp] = True

    # convert to bitmap chunks of 64 bits each
    chunks = []
    for i in range(0x110000 / CHUNK):
        chunk = 0
        for j in range(64):
            if rawdata[i * 64 + j]:
                chunk |= 1 << j
        chunks.append(chunk)

    pub_string = ""
    if is_pub:
        pub_string = "pub "
    f.write("    %sconst %s: &'static super::BoolTrie = &super::BoolTrie {\n" % (pub_string, name))
    f.write("        r1: [\n")
    data = ','.join('0x%016x' % chunk for chunk in chunks[0:0x800 / CHUNK])
    format_table_content(f, data, 12)
    f.write("\n        ],\n")

    # 0x800..0x10000 trie
    (r2, r3) = compute_trie(chunks[0x800 / CHUNK : 0x10000 / CHUNK], 64 / CHUNK)
    f.write("        r2: [\n")
    data = ','.join(str(node) for node in r2)
    format_table_content(f, data, 12)
    f.write("\n        ],\n")
    f.write("        r3: &[\n")
    data = ','.join('0x%016x' % chunk for chunk in r3)
    format_table_content(f, data, 12)
    f.write("\n        ],\n")

    # 0x10000..0x110000 trie
    (mid, r6) = compute_trie(chunks[0x10000 / CHUNK : 0x110000 / CHUNK], 64 / CHUNK)
    (r4, r5) = compute_trie(mid, 64)
    f.write("        r4: [\n")
    data = ','.join(str(node) for node in r4)
    format_table_content(f, data, 12)
    f.write("\n        ],\n")
    f.write("        r5: &[\n")
    data = ','.join(str(node) for node in r5)
    format_table_content(f, data, 12)
    f.write("\n        ],\n")
    f.write("        r6: &[\n")
    data = ','.join('0x%016x' % chunk for chunk in r6)
    format_table_content(f, data, 12)
    f.write("\n        ],\n")

    f.write("    };\n\n")
    bytes_new += 256 + 992 + 256 + 8 * len(r3) + len(r5) + 8 * len(r6)

def emit_property_module(f, mod, tbl, emit):
    f.write("pub mod %s {\n" % mod)
    for cat in sorted(emit):
        emit_bool_trie(f, "%s_table" % cat, tbl[cat])
        f.write("    pub fn %s(c: char) -> bool {\n" % cat)
        f.write("        super::trie_lookup_range_table(c, %s_table)\n" % cat)
        f.write("    }\n\n")
    f.write("}\n\n")

def emit_conversions_module(f, to_upper, to_lower, to_title):
    f.write("pub mod conversions {")
    f.write("""
    use core::option::Option;
    use core::option::Option::{Some, None};

    pub fn to_lower(c: char) -> [char; 3] {
        match bsearch_case_table(c, to_lowercase_table) {
            None        => [c, '\\0', '\\0'],
            Some(index) => to_lowercase_table[index].1,
        }
    }

    pub fn to_upper(c: char) -> [char; 3] {
        match bsearch_case_table(c, to_uppercase_table) {
            None        => [c, '\\0', '\\0'],
            Some(index) => to_uppercase_table[index].1,
        }
    }

    fn bsearch_case_table(c: char, table: &'static [(char, [char; 3])]) -> Option<usize> {
        table.binary_search_by(|&(key, _)| key.cmp(&c)).ok()
    }

""")
    t_type = "&'static [(char, [char; 3])]"
    pfun = lambda x: "(%s,[%s,%s,%s])" % (
        escape_char(x[0]), escape_char(x[1][0]), escape_char(x[1][1]), escape_char(x[1][2]))
    emit_table(f, "to_lowercase_table",
        sorted(to_lower.iteritems(), key=operator.itemgetter(0)),
        is_pub=False, t_type = t_type, pfun=pfun)
    emit_table(f, "to_uppercase_table",
        sorted(to_upper.iteritems(), key=operator.itemgetter(0)),
        is_pub=False, t_type = t_type, pfun=pfun)
    f.write("}\n\n")

def emit_norm_module(f, canon, compat, combine, norm_props):
    canon_keys = canon.keys()
    canon_keys.sort()

    compat_keys = compat.keys()
    compat_keys.sort()

    canon_comp = {}
    comp_exclusions = norm_props["Full_Composition_Exclusion"]
    for char in canon_keys:
        if True in map(lambda (lo, hi): lo <= char <= hi, comp_exclusions):
            continue
        decomp = canon[char]
        if len(decomp) == 2:
            if not canon_comp.has_key(decomp[0]):
                canon_comp[decomp[0]] = []
            canon_comp[decomp[0]].append( (decomp[1], char) )
    canon_comp_keys = canon_comp.keys()
    canon_comp_keys.sort()

if __name__ == "__main__":
    r = "tables.rs"
    if os.path.exists(r):
        os.remove(r)
    with open(r, "w") as rf:
        # write the file's preamble
        rf.write(preamble)

        # download and parse all the data
        fetch("ReadMe.txt")
        with open("ReadMe.txt") as readme:
            pattern = "for Version (\d+)\.(\d+)\.(\d+) of the Unicode"
            unicode_version = re.search(pattern, readme.read()).groups()
        rf.write("""
/// The version of [Unicode](http://www.unicode.org/)
/// that the unicode parts of `CharExt` and `UnicodeStrPrelude` traits are based on.
pub const UNICODE_VERSION: (u64, u64, u64) = (%s, %s, %s);
""" % unicode_version)
        (canon_decomp, compat_decomp, gencats, combines,
                to_upper, to_lower, to_title) = load_unicode_data("UnicodeData.txt")
        load_special_casing("SpecialCasing.txt", to_upper, to_lower, to_title)
        want_derived = ["XID_Start", "XID_Continue", "Alphabetic", "Lowercase", "Uppercase",
                        "Cased", "Case_Ignorable"]
        derived = load_properties("DerivedCoreProperties.txt", want_derived)
        scripts = load_properties("Scripts.txt", [])
        props = load_properties("PropList.txt",
                ["White_Space", "Join_Control", "Noncharacter_Code_Point", "Pattern_White_Space"])
        norm_props = load_properties("DerivedNormalizationProps.txt",
                     ["Full_Composition_Exclusion"])

        # trie_lookup_table is used in all the property modules below
        emit_trie_lookup_range_table(rf)
        # emit_bsearch_range_table(rf)

        # category tables
        for (name, cat, pfuns) in ("general_category", gencats, ["N", "Cc"]), \
                                  ("derived_property", derived, want_derived), \
                                  ("property", props, ["White_Space", "Pattern_White_Space"]):
            emit_property_module(rf, name, cat, pfuns)

        # normalizations and conversions module
        emit_norm_module(rf, canon_decomp, compat_decomp, combines, norm_props)
        emit_conversions_module(rf, to_upper, to_lower, to_title)
    #print 'bytes before = %d, bytes after = %d' % (bytes_old, bytes_new)
