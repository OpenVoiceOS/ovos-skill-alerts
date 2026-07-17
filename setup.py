# NEON AI (TM) SOFTWARE, Software Development Kit & Application Framework
# All trademark and other rights reserved by their respective owners
# Copyright 2008-2022 Neongecko.com Inc.
# Contributors: Daniel McKnight, Guy Daniels, Elon Gasper, Richard Leeds,
# Regina Bloomstine, Casimiro Ferreira, Andrii Pernatii, Kirill Hrymailo
# BSD-3 License
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS  BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS;  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE,  EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from setuptools import setup
from os import getenv, path, walk


URL = "https://github.com/OpenVoiceOS/ovos-skill-alerts"
SKILL_CLAZZ = "AlertSkill"

AUTHOR, SKILL_NAME = URL.split(".com/")[-1].split("/")
ADDITIONAL_AUTHORS = ["Emphasize"]
AUTHORS = ADDITIONAL_AUTHORS + [AUTHOR]

SKILL_PKG = SKILL_NAME.lower().replace('-', '_')
PLUGIN_ENTRY_POINT = f'{SKILL_NAME.lower()}.{AUTHOR.lower()}={SKILL_PKG}:{SKILL_CLAZZ}'
BASE_PATH = path.abspath(path.dirname(__file__))


def get_version():
    """ Find the version of the package"""
    version = None
    version_file = path.join(BASE_PATH, 'version.py')
    major, minor, build, alpha = (None, None, None, None)
    with open(version_file) as f:
        for line in f:
            if 'VERSION_MAJOR' in line:
                major = line.split('=')[1].strip()
            elif 'VERSION_MINOR' in line:
                minor = line.split('=')[1].strip()
            elif 'VERSION_BUILD' in line:
                build = line.split('=')[1].strip()
            elif 'VERSION_ALPHA' in line:
                alpha = line.split('=')[1].strip()

            if ((major and minor and build and alpha) or
                    '# END_VERSION_BLOCK' in line):
                break
    version = f"{major}.{minor}.{build}"
    if alpha and int(alpha) > 0:
        version += f"a{alpha}"
    return version


def get_requirements(requirements_filename: str):
    requirements_file = path.join(path.abspath(path.dirname(__file__)),
                                  requirements_filename)
    with open(requirements_file, 'r', encoding='utf-8') as r:
        requirements = r.readlines()
    requirements = [r.strip() for r in requirements if r.strip()
                    and not r.strip().startswith("#")]

    for i in range(0, len(requirements)):
        r = requirements[i]
        if "@" in r:
            parts = [p.lower() if p.strip().startswith("git+http") else p
                     for p in r.split('@')]
            r = "@".join(parts)
        if getenv("GITHUB_TOKEN"):
            if "github.com" in r:
                requirements[i] = \
                    r.replace("github.com",
                              f"{getenv('GITHUB_TOKEN')}@github.com")
    return requirements


def find_resource_files():
    resource_base_dirs = ("locale", "gui", "res")
    package_data = ["skill.json"]
    for res in resource_base_dirs:
        if path.isdir(path.join(BASE_PATH, res)):
            for (directory, _, files) in walk(path.join(BASE_PATH, res)):
                if files:
                    package_data.append(
                        path.join(directory.replace(BASE_PATH, "").lstrip('/'),
                                  '*'))
    return package_data


with open(path.join(path.abspath(path.dirname(__file__)), "README.md"), "r") as f:
    long_description = f.read()


setup(
    name=SKILL_NAME,
    version=get_version(),
    url=URL,
    license='BSD-3-Clause',
    install_requires=get_requirements("requirements.txt"),
    extras_require={
        "test": ["mock", "ovoscope>=0.7.0", "ovos-adapt-parser",
                 "ovos-spec-tools>=1.5.0a1"],
        "dev": ["mock", "ovoscope>=0.7.0", "ovos-adapt-parser"],
    },
    author=",".join(AUTHORS),
    author_email='',
    long_description=long_description,
    long_description_content_type="text/markdown",
    package_dir={SKILL_PKG: ""},
    packages=[SKILL_PKG, f"{SKILL_PKG}.util"],
    package_data={SKILL_PKG: find_resource_files()},
    include_package_data=True,
    entry_points={"opm.skill": PLUGIN_ENTRY_POINT}
)
