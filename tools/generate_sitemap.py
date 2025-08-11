import os
import argparse

def generate_sitemap(root_dir, out_file, indexes=False):
    urls = []
    for subdir, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".md"):
                rel_path = os.path.relpath(os.path.join(subdir, file), root_dir)
                urls.append(rel_path.replace(os.sep, "/"))
    with open(out_file, "w", encoding="utf-8") as f:
        for url in sorted(urls):
            f.write(url + "\n")
    print(f"Sitemap generated: {out_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="sitemap.txt")
    parser.add_argument("--indexes", action="store_true")
    args = parser.parse_args()
    generate_sitemap(args.root, args.out, args.indexes)
