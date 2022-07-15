from PIL import Image, ImageDraw
import numpy as np


#%% Create new image
row, col = 15, 15
margin = 80
room = 51
img = Image.new('RGB', (margin*2 + room*(col-1) + 1, margin*2 + room*(row-1) + 1), color='white')  # 535x535

# Make ImageDraw instance
draw = ImageDraw.Draw(img)

#%% Draw diagonal gradient
top_left_color = np.array([246, 205, 99])
# bottom_right_color = np.array([180, 132, 50])
bottom_right_color = np.array([200, 145, 65])
loop_num = img.size[0] + img.size[1] - 1
for i in range(loop_num):
    color = top_left_color + round(i * 12 / loop_num) / 12 * (bottom_right_color - top_left_color)
    color = np.rint(color % 256)
    color = tuple(round(c) for c in color)
    draw.line([(0, i), (i, 0)], fill=color)

# bg_colors = [(246 - i, 205 - i, 99 - i) for i in range(10)]


#%% Draw lines
# line_color = (47, 29, 9)
line_color = (136, 84, 26)
for i in range(row):
    draw.line([(margin, margin + room*i), (img.size[0] - margin - 1, margin + room*i)], fill=line_color)
for j in range(col):
    draw.line([(margin + room*j, margin), (margin + room*j, img.size[1] - margin - 1)], fill=line_color)

# Draw bold lines
# bold_line_color = (136, 84, 26)
bold_line_color = line_color
draw.line([(margin, margin), (margin + room*14, margin)], fill=bold_line_color, width=3, joint='curve')
draw.line([(margin, margin + room*14), (margin + room*14, margin + room*14)], fill=bold_line_color, width=3, joint='curve')
draw.line([(margin, margin), (margin, margin + room*14)], fill=bold_line_color, width=3, joint='curve')
draw.line([(margin + room*14, margin), (margin + room*14, margin + room*14)], fill=bold_line_color, width=3, joint='curve')

#%% Draw flower points (star points)
draw.ellipse([(margin + room*3  - 3, margin + room*3  - 3), (margin + room*3  + 3, margin + room*3  + 3)], fill=line_color)
draw.ellipse([(margin + room*11 - 3, margin + room*3  - 3), (margin + room*11 + 3, margin + room*3  + 3)], fill=line_color)
draw.ellipse([(margin + room*3  - 3, margin + room*11 - 3), (margin + room*3  + 3, margin + room*11 + 3)], fill=line_color)
draw.ellipse([(margin + room*11 - 3, margin + room*11 - 3), (margin + room*11 + 3, margin + room*11 + 3)], fill=line_color)
draw.ellipse([(margin + room*7  - 3, margin + room*7  - 3), (margin + room*7  + 3, margin + room*7  + 3)], fill=line_color)

#%% Save board image
img.save('board-PIL-step.png')
