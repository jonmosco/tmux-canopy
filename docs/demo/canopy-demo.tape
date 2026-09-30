# tmux-canopy demo - simple terminal recording
# Run from repo root: vhs docs/demo/canopy-demo.tape

Output docs/assets/canopy-demo.gif

Set Shell bash
Set FontFamily "Hack Nerd Font Mono"
Set FontSize 14
Set Width 1200
Set Height 700
Set Padding 20
Set Framerate 30
Set Theme "Dracula"
Set CursorBlink false
Set TypingSpeed 50ms
Set WindowBar Colorful
Set WindowBarSize 40

# Start tmux
Type "tmux new-session -s demo"
Enter
Sleep 2s

# Split horizontally
Ctrl+b
Sleep 200ms
Type "%"
Sleep 1s

# Run something in the right pane
Type "echo 'Hello from pane 2'"
Enter
Sleep 1s

# Go back to left pane
Ctrl+b
Sleep 200ms
Left
Sleep 1s

# Open Canopy
Ctrl+b
Sleep 200ms
Type "T"
Sleep 3s

# Let it sit for a moment
Sleep 2s
