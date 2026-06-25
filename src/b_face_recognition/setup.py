import os
from glob import glob
from setuptools import setup

package_name = 'b_face_recognition'
data_files = [
    ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
    ('share/' + package_name, ['package.xml']),
    (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
]

facial_db_files = glob('data/*.npz')
if facial_db_files:
    data_files.append(('share/' + package_name + '/data', facial_db_files))

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=data_files,
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='unitree',
    maintainer_email='unitree@todo.todo',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'face_node = b_face_recognition.face_node:main',
        ],
    },
)
