*** Test Cases ***
Section 2 CA Basic Test
    [Documentation]    Verifies the basic test case in Section 2 file ca executes successfully.
    [Tags]    section-2    smoke
    Should Be Equal    hello    hello

Section 2 CA Different Values Test
    [Documentation]    Verifies that two distinct sample values are not equal.
    [Tags]    section-2    regression
    Should Not Be Equal    open    closed

Section 2 Command Line Variables Test
    [Documentation]    Verifies user-defined variables can be supplied to the Robot Framework run.
    [Tags]    section-2    variables
    Log    ENV=${ENV}
    Log    USER=${USER}
    Log    TIMEOUT=${TIMEOUT}
    Log    ${CLI_TEXT}
    Log Many    @{CLI_LIST}
    Log    ${CLI_SET}
    Log    ${CLI_TUPLE}
    Log    ${CLI_DICTIONARY}