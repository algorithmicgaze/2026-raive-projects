cmake_minimum_required(VERSION 3.19)

set(CMAKE_OSX_ARCHITECTURES arm64)
set(CMAKE_OSX_DEPLOYMENT_TARGET "14.0" CACHE STRING "Minimum macOS version")
set(C74_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../../externals")
set(DEPS "${CMAKE_CURRENT_SOURCE_DIR}/../../deps")

include("${DEPS}/max-sdk-base/script/max-pretarget.cmake")

include_directories(${C74_INCLUDES})
set_source_files_properties(emo_core.m PROPERTIES COMPILE_FLAGS "-fobjc-arc")

add_library(${PROJECT_NAME} MODULE emotion2vec~.c emo_core.m)
target_link_libraries(${PROJECT_NAME} PRIVATE "-framework CoreML" "-framework Foundation")

include("${DEPS}/max-sdk-base/script/max-posttarget.cmake")

add_executable(emo_test test_core.c emo_core.m)
target_link_libraries(emo_test PRIVATE "-framework CoreML" "-framework Foundation")
