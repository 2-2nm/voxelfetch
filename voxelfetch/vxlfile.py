import struct

MAGIC = b"VXL"

FLAG_EDGE_COLORS = 1
INK_NONE, INK_MONO, INK_FULL, INK_CUSTOM = 0, 1, 2, 3
INK_MODES = (INK_NONE, INK_MONO, INK_FULL, INK_CUSTOM)

_HEADER_V1 = struct.Struct("<3sBB3fHH")
_HEADER_V2 = struct.Struct("<3sBB3fHHHH")
_HEADER_V3 = struct.Struct("<3sBB3fHHHH4B")
_HEADERS = {1: _HEADER_V1, 2: _HEADER_V2, 3: _HEADER_V3}
_VERTEX = struct.Struct("<3f")
_EDGE = struct.Struct("<2H")
_EDGE_COLOR = struct.Struct("<4B")

_CUBE_VERTICES = [
    (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
    (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
]
_CUBE_EDGES = [
    (0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6),
    (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7),
]


def decode(data):
    if len(data) < 4:
        raise ValueError("file is too short to be a VXL model")
    if data[:3] != MAGIC:
        raise ValueError("not a VXL file")
    version = data[3]
    header = _HEADERS.get(version)
    if header is None:
        raise ValueError(f"unsupported VXL version {version}")
    if len(data) < header.size:
        raise ValueError("file is too short to be a VXL model")
    fields = header.unpack_from(data)
    flags = fields[2]
    sx, sy, sz, nv, ne = fields[3:8]
    render = (fields[8], fields[9]) if version >= 2 and fields[8] > 0 and fields[9] > 0 else None
    ink = None
    if version >= 3 and fields[10] != INK_NONE:
        if fields[10] not in INK_MODES:
            raise ValueError(f"unknown VXL ink mode {fields[10]}")
        ink = (fields[10], tuple(fields[11:14]))
    painted = version >= 3 and bool(flags & FLAG_EDGE_COLORS)
    vertex_end = header.size + nv * _VERTEX.size
    edge_end = vertex_end + ne * _EDGE.size
    if len(data) != edge_end + (ne * _EDGE_COLOR.size if painted else 0):
        raise ValueError("VXL size does not match its header")
    vertices = list(_VERTEX.iter_unpack(data[header.size:vertex_end]))
    edges = list(_EDGE.iter_unpack(data[vertex_end:edge_end]))
    if edges and max(max(e) for e in edges) >= nv:
        raise ValueError("VXL edge references a missing vertex")
    edge_colors = [None] * ne
    if painted:
        for i, (flag, r, g, b) in enumerate(_EDGE_COLOR.iter_unpack(data[edge_end:])):
            if flag:
                edge_colors[i] = (r, g, b)
    return vertices, edges, (sx, sy, sz), render, ink, edge_colors


def load(path):
    with open(path, "rb") as f:
        return decode(f.read())


def builtin_cube():
    return list(_CUBE_VERTICES), list(_CUBE_EDGES), (0.0, 0.0, 0.0), None, None, [None] * len(_CUBE_EDGES)
