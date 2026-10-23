*** Settings ***
Library    Collections

*** Variables ***
${SECTION_3_INTEGER}    ${{100}}
${SECTION_3_FLOAT}    ${{7.25}}
${SECTION_3_CHARACTER}    T
${SECTION_3_TEXT}    sample section 3
&{SECTION_3_DATA}    section=Section 3    count=${{4}}    status=ready
${SECTION_3_LABEL}    robot test sample
${SECTION_3_RETRY_LIMIT}    ${{3}}
@{SECTION_3_LIST}    first    second    third
${SECTION_3_TUPLE}    ${{("east", 24, 3.5)}}
${SECTION_3_SET}    ${{set(["circle", "square", "triangle"])}}
${SECTION_3_COMBINED}    ${SECTION_3_TEXT} - ${SECTION_3_CHARACTER}