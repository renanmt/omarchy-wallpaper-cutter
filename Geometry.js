.pragma library

// Add a gap only across touching edges with overlapping spans. Propagate shifts
// through rows/columns so a chain of displays keeps every seam the same width.
function frames(monitors, gap, adjustments) {
    var result = monitors.map(function(m) { return Object.assign({}, m); });
    ["x", "y"].forEach(function(axis) {
        var other = axis === "x" ? "y" : "x";
        var size = axis === "x" ? "width" : "height";
        var otherSize = axis === "x" ? "height" : "width";
        var sorted = monitors.slice().sort(function(a,b) { return a[axis] - b[axis]; });
        var shifts = {};
        sorted.forEach(function(m) {
            var shift = 0;
            sorted.forEach(function(p) {
                if (p.name === m.name || p[axis] >= m[axis]) return;
                var overlap = Math.min(p[other]+p[otherSize], m[other]+m[otherSize]) - Math.max(p[other], m[other]);
                if (overlap > 0 && Math.abs(p[axis]+p[size]-m[axis]) <= 1)
                    shift = Math.max(shift, (shifts[p.name] || 0) + gap);
            });
            shifts[m.name] = shift;
        });
        result.forEach(function(m) { m[axis] += shifts[m.name] || 0; });
    });
    result.forEach(function(m) {
        var a = adjustments[m.name] || {x:0,y:0};
        m.x += a.x; m.y += a.y;
    });
    return result;
}
function bounds(frames) {
    if (!frames.length) return {x:0,y:0,width:1920,height:1080};
    var x = Math.min.apply(null, frames.map(function(m) {return m.x;}));
    var y = Math.min.apply(null, frames.map(function(m) {return m.y;}));
    return {x:x,y:y,width:Math.max.apply(null,frames.map(function(m){return m.x+m.width;}))-x,
        height:Math.max.apply(null,frames.map(function(m){return m.y+m.height;}))-y};
}
