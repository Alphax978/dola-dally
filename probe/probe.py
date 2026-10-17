import prepare_frames as p, random
items = p.gallery_items()
print("TOTAL", len(items)); print(random.sample(items, 5))
open("probe/count.txt", "w").write(f"{len(items)}\n")
