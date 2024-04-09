import requests
import json
import os
import sys
import re

BASE_URL = 'https://studien.rj.ost.ch/'
OUTPUT_DIRECTORY = 'data'

content = requests.get(f'{BASE_URL}allStudies/10191_I.json').content
jsonContent = json.loads(content)

categories = {}
modules = {}
focuses = []

def getIdForModule(kuerzel):
    return kuerzel.removeprefix('M_')

def getIdForCategory(kuerzel):
    return kuerzel.removeprefix('I-').removeprefix('I_').removeprefix('Kat_')

def getAdmissionCondition(co):
    coo = co.replace('&nbsp;', ' ').replace('&ouml;', 'ö').replace('&uuml;', 'ü').replace('&Uuml;', 'Ü').replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n').replace('<p>', '').replace('</p>', '')

    pattern = r'[\n:;]'
    sp = re.split(pattern, coo)
        
    return sp[0]


# 'kredits' contains categories
kredits = jsonContent['kredits']
for kredit in kredits:
    category = kredit['kategorien'][0]
    catId = getIdForCategory(category['kuerzel'])
    categories[catId] = {
        'id': catId,
        'required_ects': kredit['minKredits'],
        'name': category['bezeichnung'],
        'total_ects': 0,
        'modules': [],
    }


# 'zuordnungen' contains modules
zuordnungen = jsonContent['zuordnungen']
for zuordnung in zuordnungen:
    module = {
        'id': getIdForModule(zuordnung['kuerzel']),
        'name': zuordnung['bezeichnung'],
        'url': zuordnung['url'],
        'isThesis': zuordnung['istAbschlussArbeit'],
        'isRequired': zuordnung['istPflichtmodul'],
        'recommendedSemester': zuordnung['semEmpfehlung'],
        'focuses': [],
        'categories': [],
        'ects': 0,
        'isDeactivated': False
        }

    if 'kategorien' in zuordnung:
        module['categories'] = [{ 'id': getIdForCategory(z['kuerzel']), 'name': z['bezeichnung'], 'ects': z['kreditpunkte'] } for z in zuordnung['kategorien']]
        module['ects'] = zuordnung['kategorien'][0]['kreditpunkte']
        
    modules[module['id']] = module


# load more infos about modules
for module in modules.values():
    moduleContent = json.loads(requests.get(f'{BASE_URL}{module["url"]}').content)

    # needed for modules, whose credits do not count towards "Studiengang Informatik"
    if 'kreditpunkte' in moduleContent and module['ects'] == 0:
        module['ects'] = moduleContent['kreditpunkte']
    
    if 'zustand' in moduleContent and moduleContent['zustand'] == 'deaktiviert':
        module['isDeactivated'] = True
        continue

    if 'voraussetzungen' in moduleContent:
        req = list(map(lambda m: {
            'id': getIdForModule(m['kuerzel']),
            'name': m['bezeichnung'],
            'url': m['url']
        }, moduleContent['voraussetzungen']))
        module['requiredModules'] = req

    # if 'sprache' in moduleContent:
    #     module['language'] = moduleContent['sprache']
    if 'english' in module['name'].lower() or ('vorausgKenntnisse' in moduleContent and 'english' in moduleContent['vorausgKenntnisse'].lower()):
        module['language'] = 'english'
    else:
        module['language'] = 'german'

    module['evaluation'] = []
    if 'semesterBewertung' in moduleContent:
        if moduleContent['semesterBewertung'] == 'Note von 1 - 6':
            module['evaluation'].append('semester-work-exam')
            
        if moduleContent['semesterBewertung'] == 'bestanden / nicht bestanden':
            module['evaluation'].append('semester-work-passed')

    if 'zuordnungen' in moduleContent:
        # reduce zuordnungen to those with semEmpfehlung > 0
        relations = [zuordnung['semEmpfehlung'] for zuordnung in moduleContent['zuordnungen'] if zuordnung['semEmpfehlung'] > 0]
        
        if len(relations) > 0:
            module['recommendedSemesterPartTime'] = max(relations)
            module['recommendedSemesterFullTime'] = min(relations)

    if 'pruefung' in moduleContent:
        module['evaluation'].append('semester-exam')

        for pruefung in moduleContent['pruefung']:
            if pruefung['zulassung']:
                module['semesterExamAdmissionCondition'] = getAdmissionCondition(pruefung['zulassungsBedingung'])
            else:
                module['semesterExamAdmissionCondition'] = 'none'

            semesterExamTypes = []
            if pruefung['pruefungMue']:
                semesterExamTypes.append('oral')
            
            if pruefung['pruefungSchr']:
                semesterExamTypes.append('written')

            
            module['semesterExamType'] = semesterExamTypes

    if 'durchfuehrungen' in moduleContent:
        semesterBegin = moduleContent['durchfuehrungen']['beginSemester'].replace('HS', 'fall').replace('FS', 'spring')
        semesterEnd = moduleContent['durchfuehrungen']['endSemester'].replace('HS', 'fall').replace('FS', 'spring')
        
        if semesterBegin == semesterEnd:
            module['semester'] = [semesterBegin]

        else:
            module['semester'] = [semesterBegin, semesterEnd]
                        
    if 'empfehlungen' in moduleContent:
        reco = list(map(lambda m: {
            'id': getIdForModule(m['kuerzel']),
            'name': m['bezeichnung'],
            'url': m['url']
        }, moduleContent['empfehlungen']))
        module['recommendedModules'] = reco

    if 'dozenten' in moduleContent:
        resp = moduleContent['dozenten']
        c = list(map(lambda r: r['vorname'] + ' ' + r['name'], resp))

        module['responsibles'] = c

    if 'categories' in module:
        for cat in module['categories']:
            categories[cat['id']]['modules'].append({'id': module['id'], 'name': module['name'],'url': module['url']})
            categories[cat['id']]['total_ects'] += module['ects']        

modules = {key: value for (key, value) in modules.items() if value['isDeactivated'] == False}

for module in modules.values():
    del module['isDeactivated']


# 'spezialisierungen' contains focuses
spezialisierungen = jsonContent['spezialisierungen']
for spez in spezialisierungen:
    focus = {
        'id': spez['kuerzel'],
        'url': spez['url'],
        'name': spez['bezeichnung'],
        'modules': []
        }
    focusContent = json.loads(requests.get(f'{BASE_URL}{spez["url"]}').content)
    for zuordnung in focusContent['zuordnungen']:
        moduleId = getIdForModule(zuordnung['kuerzel'])
        if moduleId in modules:
            focus['modules'].append({'id': moduleId, 'name': zuordnung['bezeichnung'], 'url': zuordnung['url']})
            modules[moduleId]['focuses'].append({'id': focus['id'], 'name': focus['name'], 'url': focus['url']})
    focuses.append(focus)


# id should be unique for each module
idsSet = set([m['id'] for m in modules.values()])
if len(idsSet) != len(modules):
    sys.exit(1)


modules = list(modules.values())
categories = list(categories.values())


if not os.path.exists(OUTPUT_DIRECTORY):
    os.mkdir(OUTPUT_DIRECTORY)

with open(f'{OUTPUT_DIRECTORY}/categories.json', 'w') as output:
    json.dump(categories, output, indent=2)

with open(f'{OUTPUT_DIRECTORY}/modules.json', 'w') as output:
    json.dump(modules, output, indent=2)

with open(f'{OUTPUT_DIRECTORY}/focuses.json', 'w') as output:
    json.dump(focuses, output, indent=2)
