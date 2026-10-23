*** Test Cases ***
Section 3 A2 Basic Test
    [Documentation]    Verifies the basic test case in Section 3 file a2 executes successfully.
    [Tags]    section-3    smoke
    Should Be Equal    hello    hello

Section 3 A2 Text Contains Test
    [Documentation]    Verifies that expected text can be found in a sample string.
    [Tags]    section-3    regression
    Should Contain    reliable result    result

Section 3 A2 Different Values Test
    [Documentation]    Verifies that two distinct sample values are not equal.
    [Tags]    section-3    regression
    Should Not Be Equal    enabled    disabled

Section 3 A2 Number Equality Test
    [Documentation]    Verifies equality for matching numeric text values.
    [Tags]    section-3    regression
    Should Be Equal    23    23

Section 3 A2 Exact Text Test
    [Documentation]    Verifies equality for matching sample text values.
    [Tags]    section-3    regression
    Should Be Equal    robot test    robot test