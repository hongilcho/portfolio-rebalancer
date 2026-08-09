with open("portfolio_rebalancer/pages/dashboard.py", "r", encoding="utf-8") as f:
    content = f.read()

# I will find the editor block and move it.
editor_start_marker = '        rx.heading("✏️ 보유 잔고 및 예수금 입력/수정하기"'
editor_end_marker = '        rx.heading("📂 계좌별 상세 현황"'

# The editor block starts at editor_start_marker and ends right before editor_end_marker
start_idx = content.find(editor_start_marker)
end_idx = content.find(editor_end_marker)

editor_block = content[start_idx:end_idx]
# Remove editor block from its current place
content = content[:start_idx] + content[end_idx:]

# Now find the end of the page.
# The page ends with:
#         ),
#         width="100%",
#         align_items="flex-start",
#     )
insert_marker = '        width="100%",\n        align_items="flex-start",\n    )'
content = content.replace(insert_marker, editor_block + insert_marker)

with open("portfolio_rebalancer/pages/dashboard.py", "w", encoding="utf-8") as f:
    f.write(content)
