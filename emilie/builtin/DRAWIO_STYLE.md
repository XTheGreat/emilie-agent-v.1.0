# Activity diagrams in draw.io

Use render_drawio for editable draw.io diagrams. Follow an existing user-supplied example first. The repository reference is `examples/contoh.drawio`.

Use uncompressed mxfile → diagram (name) → mxGraphModel (dx, dy, grid="1", gridSize="10", page="1", pageWidth, pageHeight) → root. Start with cells 0 and 1, with 1 parented to 0. Use unique cell IDs within each page.

Align x, y, width and height to a 10 px grid. Use 120 × 60 activities (160 × 60 for longer text) and 40 px vertical gaps. Flow down the page. Arrange equal-height actor lanes left to right, parent each node to its lane, and route inter-lane edges orthogonally around other nodes. Avoid crossings.

Use Helvetica 12. Apply these styles:

- Activity: `rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;`
- Start: black 30 × 30 circle. End: double circle or `shape=endState;fillColor=#000000;`.
- Decision and smaller merge: `rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;`
- Store: `shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=15;fillColor=#f5f5f5;strokeColor=#666666;`
- Lane: `swimlane;horizontal=0;whiteSpace=wrap;html=1;startSize=30;`
- Edge: `edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;endFill=1;`. Choose exitX/exitY/entryX/entryY and waypoints as needed. Put labels in the edge value with `labelBackgroundColor=#ffffff;`.

Default to one start and one end. Use sequential flow without fork/join. Pair every blank decision diamond with a merge. Put the check in an activity starting with “Memeriksa…” immediately before its diamond. Label its two outgoing edges True and False. Use Indonesian verb-first activities. The actor initiates, the system decides, and Database/Session Store executes. Place a “Meminta…” system activity before each database interaction.

After every successful export, you MUST open the sibling PNG (same stem as drawio_path) with read_file and inspect the image. Check overlapping boxes, clipped text, arrows crossing nodes or each other, and uneven spacing. Fix the XML and re-export when needed, inspecting every revision. Stop after three render-and-inspect rounds and report any remaining defects. If vision is unavailable, say so explicitly.
