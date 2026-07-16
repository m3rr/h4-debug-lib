from PIL import Image

img = Image.new('RGB', (100, 100), color = 'red')
exif = img.getexif()
exif[271] = "h4-debug camera" # Make
img.save('test.png', exif=exif)
print("Created test.png with EXIF")
