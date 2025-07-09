# iCloud Backup Tool

Perhaps there is an easier or more official way to do this but this worked for me. I wanted full image quality and all metadata for every picture or video I'd ever taken with an apple device to be backed up to a hard drive. To get this to run you need:

- a Mac (presumably logged into your account & w/ access to your photo library)
- python 3.12 (probably not but that's what I wrote this in)
- an external HDD/SSD and way to connect it to your Mac

You will need to give whatever version of python you are using access to your full disc.

run the osx-test.py file with a start and end date yyyy-mm-dd and a destination folder. it will create monthly folders for photos and download copies of anything from that time as well as metadata. These are copies so they can be deleted.