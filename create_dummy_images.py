#!/usr/bin/env python3
"""
Script to create thousands of dummy images for testing the dedupe pipeline.
Creates various image formats with some duplicates having different names.
"""

import os
import random
import hashlib
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math

def create_dummy_image(width=800, height=600, text="", color=None):
    """Create a dummy image with optional text and color."""
    if color is None:
        color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    
    # Create image with random background
    img = Image.new('RGB', (width, height), color)
    draw = ImageDraw.Draw(img)
    
    if text:
        try:
            # Try to use a default font
            font = ImageFont.load_default()
        except:
            font = None
        
        # Calculate text position (center)
        if font:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        else:
            text_width = len(text) * 6  # Approximate
            text_height = 11
        
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        
        # Draw text with contrasting color
        text_color = (255 - color[0], 255 - color[1], 255 - color[2])
        draw.text((x, y), text, fill=text_color, font=font)
    
    return img

def create_image_variations(base_img, count=5):
    """Create variations of a base image (different sizes, formats)."""
    variations = []
    
    # Original
    variations.append(("original", base_img))
    
    # Different sizes
    sizes = [(400, 300), (1200, 900), (200, 150), (1600, 1200)]
    for i, size in enumerate(sizes[:count-1]):
        resized = base_img.resize(size, Image.Resampling.LANCZOS)
        variations.append((f"size_{size[0]}x{size[1]}", resized))
    
    return variations

def generate_image_hash(img):
    """Generate a hash for the image content."""
    # Convert to bytes and hash
    import io
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return hashlib.md5(buffer.getvalue()).hexdigest()

def create_dummy_images(output_dir="dummy_images", total_images=5000, duplicate_ratio=0.3):
    """Create thousands of dummy images with duplicates."""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Create subdirectories
    subdirs = ["photos", "screenshots", "artwork", "documents", "memes", "wallpapers"]
    for subdir in subdirs:
        (output_path / subdir).mkdir(exist_ok=True)
    
    print(f"Creating {total_images} dummy images in {output_dir}/")
    print(f"Duplicate ratio: {duplicate_ratio:.1%}")
    
    # Track image hashes for duplicates
    image_hashes = {}
    created_count = 0
    duplicate_count = 0
    
    # Base images to duplicate
    base_images = []
    
    # Create some base images first
    print("Creating base images...")
    for i in range(50):
        # Create unique base image
        text = f"Base Image {i+1}"
        color = (random.randint(50, 200), random.randint(50, 200), random.randint(50, 200))
        img = create_dummy_image(text=text, color=color)
        base_images.append(img)
    
    # Create images
    for i in range(total_images):
        if i % 100 == 0:
            print(f"Progress: {i}/{total_images} ({i/total_images:.1%})")
        
        # Choose subdirectory
        subdir = random.choice(subdirs)
        
        # Decide if this should be a duplicate
        should_duplicate = random.random() < duplicate_ratio and len(base_images) > 0
        
        if should_duplicate and len(base_images) > 0:
            # Create a duplicate with different name
            base_img = random.choice(base_images)
            variations = create_image_variations(base_img, random.randint(2, 4))
            
            for j, (variation_name, img) in enumerate(variations):
                if created_count >= total_images:
                    break
                
                # Generate different filename
                filename = f"img_{created_count:06d}_{variation_name}_{random.randint(1000, 9999)}.png"
                filepath = output_path / subdir / filename
                
                img.save(filepath, 'PNG')
                created_count += 1
                duplicate_count += 1
                
                if created_count >= total_images:
                    break
        else:
            # Create unique image
            text = f"Image {created_count}"
            color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            img = create_dummy_image(text=text, color=color)
            
            # Random format
            formats = ['PNG', 'JPEG']
            format_choice = random.choice(formats)
            
            if format_choice == 'PNG':
                filename = f"unique_{created_count:06d}_{random.randint(1000, 9999)}.png"
                filepath = output_path / subdir / filename
                img.save(filepath, 'PNG')
            else:
                filename = f"unique_{created_count:06d}_{random.randint(1000, 9999)}.jpg"
                filepath = output_path / subdir / filename
                # Convert to RGB for JPEG
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.save(filepath, 'JPEG', quality=random.randint(70, 95))
            
            created_count += 1
    
    print(f"\n✅ Created {created_count} images")
    print(f"📁 Location: {output_path.absolute()}")
    print(f"📊 Duplicates: {duplicate_count}")
    print(f"📊 Unique: {created_count - duplicate_count}")
    
    # Show directory structure
    print(f"\n📂 Directory structure:")
    for subdir in subdirs:
        count = len(list((output_path / subdir).glob("*")))
        print(f"  {subdir}/: {count} images")
    
    return output_path

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Create dummy images for testing dedupe pipeline")
    parser.add_argument("--output", "-o", default="dummy_images", help="Output directory")
    parser.add_argument("--count", "-c", type=int, default=5000, help="Total number of images")
    parser.add_argument("--duplicates", "-d", type=float, default=0.3, help="Duplicate ratio (0.0-1.0)")
    
    args = parser.parse_args()
    
    try:
        create_dummy_images(args.output, args.count, args.duplicates)
    except KeyboardInterrupt:
        print("\n❌ Interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
