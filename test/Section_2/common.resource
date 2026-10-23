*** Settings ***
Library    Collections

*** Variables ***
${SECTION_2_INTEGER}    ${{19}}
${SECTION_2_FLOAT}    ${{2.5}}
${SECTION_2_CHARACTER}    S
${SECTION_2_TEXT}    sample section 2
&{SECTION_2_DATA}    section=Section 2    count=${{3}}    status=ready
${SECTION_2_LABEL}    regression sample
@{SECTION_2_LIST}    queued    running    complete
${SECTION_2_TUPLE}    ${{("small", 12, 2.75)}}
${SECTION_2_SET}    ${{set(["oak", "maple", "birch"])}}
${SECTION_2_COMBINED}    ${SECTION_2_TEXT} - ${SECTION_2_CHARACTER}