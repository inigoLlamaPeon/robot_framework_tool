*** Test Cases ***
Section 5 A2 Basic Test
    [Documentation]    Verifies the basic test case in Section 5 file a2 executes successfully.
    [Tags]    section-5    smoke
    Should Be Equal    hello    hello

Section 5 A2 Text Contains Test
    [Documentation]    Verifies that expected text can be found in a sample string.
    [Tags]    section-5    regression
    Should Contain    successful run    successful

Section 5 A2 Different Values Test
    [Documentation]    Verifies that two distinct sample values are not equal.
    [Tags]    section-5    regression
    Should Not Be Equal    true    false