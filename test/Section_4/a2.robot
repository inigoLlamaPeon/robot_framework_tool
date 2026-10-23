*** Test Cases ***
Section 4 A2 Basic Test
    [Documentation]    Verifies the basic test case in Section 4 file a2 executes successfully.
    [Tags]    section-4    smoke
    Should Be Equal    hello    hello

Section 4 A2 Different Values Test
    [Documentation]    Verifies that two distinct sample values are not equal.
    [Tags]    section-4    regression
    Should Not Be Equal    start    stop