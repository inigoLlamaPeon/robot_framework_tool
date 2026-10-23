*** Test Cases ***
Section 1 C1 Basic Test
    [Documentation]    Verifies the basic test case in Section 1 file c1 executes successfully.
    [Tags]    section-1    smoke
    Should Be Equal    hello    hello

Section 1 C1 Text Contains Test
    [Documentation]    Verifies that expected text can be found in a sample string.
    [Tags]    section-1    regression
    Should Contain    robot framework    robot

Section 1 Command Line Variables Test
    [Documentation]    Verifies user-defined variables can be supplied to the Robot Framework run.
    [Tags]    section-1    variables
    Log    ENV=${ENV}
    Log    USER=${USER}
    Log    TIMEOUT=${TIMEOUT}
    Log    ${CLI_TEXT}
    Log Many    @{CLI_LIST}
    Log    ${CLI_SET}
    Log    ${CLI_TUPLE}
    Log    ${CLI_DICTIONARY}