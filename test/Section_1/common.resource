*** Settings ***
Library    Collections

*** Variables ***
${SECTION_1_INTEGER}    ${{42}}
${SECTION_1_FLOAT}    ${{3.14}}
${SECTION_1_CHARACTER}    R
${SECTION_1_TEXT}    sample section 1
&{SECTION_1_DATA}    section=Section 1    count=${{2}}    status=ready
@{SECTION_1_LIST}    alpha    beta    gamma
${SECTION_1_TUPLE}    ${{("north", 2, 1.5)}}
${SECTION_1_SET}    ${{set(["red", "blue", "green"])}}
${SECTION_1_COMBINED}    ${SECTION_1_TEXT} - ${SECTION_1_CHARACTER}