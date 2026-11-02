#include "car.h"

namespace {
#define DIM 9
#define EDIM 9
#define MEDIM 9
typedef void (*Hfun)(double *, double *, double *);

double mass;

void set_mass(double x){ mass = x;}

double rotational_inertia;

void set_rotational_inertia(double x){ rotational_inertia = x;}

double center_to_front;

void set_center_to_front(double x){ center_to_front = x;}

double center_to_rear;

void set_center_to_rear(double x){ center_to_rear = x;}

double stiffness_front;

void set_stiffness_front(double x){ stiffness_front = x;}

double stiffness_rear;

void set_stiffness_rear(double x){ stiffness_rear = x;}
const static double MAHA_THRESH_25 = 3.8414588206941227;
const static double MAHA_THRESH_24 = 5.991464547107981;
const static double MAHA_THRESH_30 = 3.8414588206941227;
const static double MAHA_THRESH_26 = 3.8414588206941227;
const static double MAHA_THRESH_27 = 3.8414588206941227;
const static double MAHA_THRESH_29 = 3.8414588206941227;
const static double MAHA_THRESH_28 = 3.8414588206941227;
const static double MAHA_THRESH_31 = 3.8414588206941227;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_4525121693915560921) {
   out_4525121693915560921[0] = delta_x[0] + nom_x[0];
   out_4525121693915560921[1] = delta_x[1] + nom_x[1];
   out_4525121693915560921[2] = delta_x[2] + nom_x[2];
   out_4525121693915560921[3] = delta_x[3] + nom_x[3];
   out_4525121693915560921[4] = delta_x[4] + nom_x[4];
   out_4525121693915560921[5] = delta_x[5] + nom_x[5];
   out_4525121693915560921[6] = delta_x[6] + nom_x[6];
   out_4525121693915560921[7] = delta_x[7] + nom_x[7];
   out_4525121693915560921[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_1972415448394742236) {
   out_1972415448394742236[0] = -nom_x[0] + true_x[0];
   out_1972415448394742236[1] = -nom_x[1] + true_x[1];
   out_1972415448394742236[2] = -nom_x[2] + true_x[2];
   out_1972415448394742236[3] = -nom_x[3] + true_x[3];
   out_1972415448394742236[4] = -nom_x[4] + true_x[4];
   out_1972415448394742236[5] = -nom_x[5] + true_x[5];
   out_1972415448394742236[6] = -nom_x[6] + true_x[6];
   out_1972415448394742236[7] = -nom_x[7] + true_x[7];
   out_1972415448394742236[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_7275833948890819174) {
   out_7275833948890819174[0] = 1.0;
   out_7275833948890819174[1] = 0.0;
   out_7275833948890819174[2] = 0.0;
   out_7275833948890819174[3] = 0.0;
   out_7275833948890819174[4] = 0.0;
   out_7275833948890819174[5] = 0.0;
   out_7275833948890819174[6] = 0.0;
   out_7275833948890819174[7] = 0.0;
   out_7275833948890819174[8] = 0.0;
   out_7275833948890819174[9] = 0.0;
   out_7275833948890819174[10] = 1.0;
   out_7275833948890819174[11] = 0.0;
   out_7275833948890819174[12] = 0.0;
   out_7275833948890819174[13] = 0.0;
   out_7275833948890819174[14] = 0.0;
   out_7275833948890819174[15] = 0.0;
   out_7275833948890819174[16] = 0.0;
   out_7275833948890819174[17] = 0.0;
   out_7275833948890819174[18] = 0.0;
   out_7275833948890819174[19] = 0.0;
   out_7275833948890819174[20] = 1.0;
   out_7275833948890819174[21] = 0.0;
   out_7275833948890819174[22] = 0.0;
   out_7275833948890819174[23] = 0.0;
   out_7275833948890819174[24] = 0.0;
   out_7275833948890819174[25] = 0.0;
   out_7275833948890819174[26] = 0.0;
   out_7275833948890819174[27] = 0.0;
   out_7275833948890819174[28] = 0.0;
   out_7275833948890819174[29] = 0.0;
   out_7275833948890819174[30] = 1.0;
   out_7275833948890819174[31] = 0.0;
   out_7275833948890819174[32] = 0.0;
   out_7275833948890819174[33] = 0.0;
   out_7275833948890819174[34] = 0.0;
   out_7275833948890819174[35] = 0.0;
   out_7275833948890819174[36] = 0.0;
   out_7275833948890819174[37] = 0.0;
   out_7275833948890819174[38] = 0.0;
   out_7275833948890819174[39] = 0.0;
   out_7275833948890819174[40] = 1.0;
   out_7275833948890819174[41] = 0.0;
   out_7275833948890819174[42] = 0.0;
   out_7275833948890819174[43] = 0.0;
   out_7275833948890819174[44] = 0.0;
   out_7275833948890819174[45] = 0.0;
   out_7275833948890819174[46] = 0.0;
   out_7275833948890819174[47] = 0.0;
   out_7275833948890819174[48] = 0.0;
   out_7275833948890819174[49] = 0.0;
   out_7275833948890819174[50] = 1.0;
   out_7275833948890819174[51] = 0.0;
   out_7275833948890819174[52] = 0.0;
   out_7275833948890819174[53] = 0.0;
   out_7275833948890819174[54] = 0.0;
   out_7275833948890819174[55] = 0.0;
   out_7275833948890819174[56] = 0.0;
   out_7275833948890819174[57] = 0.0;
   out_7275833948890819174[58] = 0.0;
   out_7275833948890819174[59] = 0.0;
   out_7275833948890819174[60] = 1.0;
   out_7275833948890819174[61] = 0.0;
   out_7275833948890819174[62] = 0.0;
   out_7275833948890819174[63] = 0.0;
   out_7275833948890819174[64] = 0.0;
   out_7275833948890819174[65] = 0.0;
   out_7275833948890819174[66] = 0.0;
   out_7275833948890819174[67] = 0.0;
   out_7275833948890819174[68] = 0.0;
   out_7275833948890819174[69] = 0.0;
   out_7275833948890819174[70] = 1.0;
   out_7275833948890819174[71] = 0.0;
   out_7275833948890819174[72] = 0.0;
   out_7275833948890819174[73] = 0.0;
   out_7275833948890819174[74] = 0.0;
   out_7275833948890819174[75] = 0.0;
   out_7275833948890819174[76] = 0.0;
   out_7275833948890819174[77] = 0.0;
   out_7275833948890819174[78] = 0.0;
   out_7275833948890819174[79] = 0.0;
   out_7275833948890819174[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_7956715178949728761) {
   out_7956715178949728761[0] = state[0];
   out_7956715178949728761[1] = state[1];
   out_7956715178949728761[2] = state[2];
   out_7956715178949728761[3] = state[3];
   out_7956715178949728761[4] = state[4];
   out_7956715178949728761[5] = dt*((-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]))*state[6] - 9.8100000000000005*state[8] + stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*state[1]) + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*state[4])) + state[5];
   out_7956715178949728761[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_7956715178949728761[7] = state[7];
   out_7956715178949728761[8] = state[8];
}
void F_fun(double *state, double dt, double *out_4817379664253254158) {
   out_4817379664253254158[0] = 1;
   out_4817379664253254158[1] = 0;
   out_4817379664253254158[2] = 0;
   out_4817379664253254158[3] = 0;
   out_4817379664253254158[4] = 0;
   out_4817379664253254158[5] = 0;
   out_4817379664253254158[6] = 0;
   out_4817379664253254158[7] = 0;
   out_4817379664253254158[8] = 0;
   out_4817379664253254158[9] = 0;
   out_4817379664253254158[10] = 1;
   out_4817379664253254158[11] = 0;
   out_4817379664253254158[12] = 0;
   out_4817379664253254158[13] = 0;
   out_4817379664253254158[14] = 0;
   out_4817379664253254158[15] = 0;
   out_4817379664253254158[16] = 0;
   out_4817379664253254158[17] = 0;
   out_4817379664253254158[18] = 0;
   out_4817379664253254158[19] = 0;
   out_4817379664253254158[20] = 1;
   out_4817379664253254158[21] = 0;
   out_4817379664253254158[22] = 0;
   out_4817379664253254158[23] = 0;
   out_4817379664253254158[24] = 0;
   out_4817379664253254158[25] = 0;
   out_4817379664253254158[26] = 0;
   out_4817379664253254158[27] = 0;
   out_4817379664253254158[28] = 0;
   out_4817379664253254158[29] = 0;
   out_4817379664253254158[30] = 1;
   out_4817379664253254158[31] = 0;
   out_4817379664253254158[32] = 0;
   out_4817379664253254158[33] = 0;
   out_4817379664253254158[34] = 0;
   out_4817379664253254158[35] = 0;
   out_4817379664253254158[36] = 0;
   out_4817379664253254158[37] = 0;
   out_4817379664253254158[38] = 0;
   out_4817379664253254158[39] = 0;
   out_4817379664253254158[40] = 1;
   out_4817379664253254158[41] = 0;
   out_4817379664253254158[42] = 0;
   out_4817379664253254158[43] = 0;
   out_4817379664253254158[44] = 0;
   out_4817379664253254158[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/(mass*state[1]) + (-stiffness_front - stiffness_rear)*state[5]/(mass*state[4]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/(mass*state[4]));
   out_4817379664253254158[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*pow(state[1], 2));
   out_4817379664253254158[47] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_4817379664253254158[48] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_4817379664253254158[49] = dt*((-1 - (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*pow(state[4], 2)))*state[6] - (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*pow(state[4], 2)));
   out_4817379664253254158[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/(mass*state[4]) + 1;
   out_4817379664253254158[51] = dt*(-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]));
   out_4817379664253254158[52] = dt*stiffness_front*state[0]/(mass*state[1]);
   out_4817379664253254158[53] = -9.8100000000000005*dt;
   out_4817379664253254158[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_4817379664253254158[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_4817379664253254158[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_4817379664253254158[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_4817379664253254158[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_4817379664253254158[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_4817379664253254158[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_4817379664253254158[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_4817379664253254158[62] = 0;
   out_4817379664253254158[63] = 0;
   out_4817379664253254158[64] = 0;
   out_4817379664253254158[65] = 0;
   out_4817379664253254158[66] = 0;
   out_4817379664253254158[67] = 0;
   out_4817379664253254158[68] = 0;
   out_4817379664253254158[69] = 0;
   out_4817379664253254158[70] = 1;
   out_4817379664253254158[71] = 0;
   out_4817379664253254158[72] = 0;
   out_4817379664253254158[73] = 0;
   out_4817379664253254158[74] = 0;
   out_4817379664253254158[75] = 0;
   out_4817379664253254158[76] = 0;
   out_4817379664253254158[77] = 0;
   out_4817379664253254158[78] = 0;
   out_4817379664253254158[79] = 0;
   out_4817379664253254158[80] = 1;
}
void h_25(double *state, double *unused, double *out_147038242079145023) {
   out_147038242079145023[0] = state[6];
}
void H_25(double *state, double *unused, double *out_8151142693229822154) {
   out_8151142693229822154[0] = 0;
   out_8151142693229822154[1] = 0;
   out_8151142693229822154[2] = 0;
   out_8151142693229822154[3] = 0;
   out_8151142693229822154[4] = 0;
   out_8151142693229822154[5] = 0;
   out_8151142693229822154[6] = 1;
   out_8151142693229822154[7] = 0;
   out_8151142693229822154[8] = 0;
}
void h_24(double *state, double *unused, double *out_4380945631886811145) {
   out_4380945631886811145[0] = state[4];
   out_4380945631886811145[1] = state[5];
}
void H_24(double *state, double *unused, double *out_6737675781677406326) {
   out_6737675781677406326[0] = 0;
   out_6737675781677406326[1] = 0;
   out_6737675781677406326[2] = 0;
   out_6737675781677406326[3] = 0;
   out_6737675781677406326[4] = 1;
   out_6737675781677406326[5] = 0;
   out_6737675781677406326[6] = 0;
   out_6737675781677406326[7] = 0;
   out_6737675781677406326[8] = 0;
   out_6737675781677406326[9] = 0;
   out_6737675781677406326[10] = 0;
   out_6737675781677406326[11] = 0;
   out_6737675781677406326[12] = 0;
   out_6737675781677406326[13] = 0;
   out_6737675781677406326[14] = 1;
   out_6737675781677406326[15] = 0;
   out_6737675781677406326[16] = 0;
   out_6737675781677406326[17] = 0;
}
void h_30(double *state, double *unused, double *out_3784487770333167373) {
   out_3784487770333167373[0] = state[4];
}
void H_30(double *state, double *unused, double *out_7777268421972480835) {
   out_7777268421972480835[0] = 0;
   out_7777268421972480835[1] = 0;
   out_7777268421972480835[2] = 0;
   out_7777268421972480835[3] = 0;
   out_7777268421972480835[4] = 1;
   out_7777268421972480835[5] = 0;
   out_7777268421972480835[6] = 0;
   out_7777268421972480835[7] = 0;
   out_7777268421972480835[8] = 0;
}
void h_26(double *state, double *unused, double *out_1858242100747789462) {
   out_1858242100747789462[0] = state[7];
}
void H_26(double *state, double *unused, double *out_4409639374355765930) {
   out_4409639374355765930[0] = 0;
   out_4409639374355765930[1] = 0;
   out_4409639374355765930[2] = 0;
   out_4409639374355765930[3] = 0;
   out_4409639374355765930[4] = 0;
   out_4409639374355765930[5] = 0;
   out_4409639374355765930[6] = 0;
   out_4409639374355765930[7] = 1;
   out_4409639374355765930[8] = 0;
}
void h_27(double *state, double *unused, double *out_8970756540361744684) {
   out_8970756540361744684[0] = state[3];
}
void H_27(double *state, double *unused, double *out_8494712339936645870) {
   out_8494712339936645870[0] = 0;
   out_8494712339936645870[1] = 0;
   out_8494712339936645870[2] = 0;
   out_8494712339936645870[3] = 1;
   out_8494712339936645870[4] = 0;
   out_8494712339936645870[5] = 0;
   out_8494712339936645870[6] = 0;
   out_8494712339936645870[7] = 0;
   out_8494712339936645870[8] = 0;
}
void h_29(double *state, double *unused, double *out_8786161037994013018) {
   out_8786161037994013018[0] = state[1];
}
void H_29(double *state, double *unused, double *out_7267037077658088651) {
   out_7267037077658088651[0] = 0;
   out_7267037077658088651[1] = 1;
   out_7267037077658088651[2] = 0;
   out_7267037077658088651[3] = 0;
   out_7267037077658088651[4] = 0;
   out_7267037077658088651[5] = 0;
   out_7267037077658088651[6] = 0;
   out_7267037077658088651[7] = 0;
   out_7267037077658088651[8] = 0;
}
void h_28(double *state, double *unused, double *out_3833257662266850097) {
   out_3833257662266850097[0] = state[0];
}
void H_28(double *state, double *unused, double *out_6097307978981932391) {
   out_6097307978981932391[0] = 1;
   out_6097307978981932391[1] = 0;
   out_6097307978981932391[2] = 0;
   out_6097307978981932391[3] = 0;
   out_6097307978981932391[4] = 0;
   out_6097307978981932391[5] = 0;
   out_6097307978981932391[6] = 0;
   out_6097307978981932391[7] = 0;
   out_6097307978981932391[8] = 0;
}
void h_31(double *state, double *unused, double *out_128155820205360866) {
   out_128155820205360866[0] = state[8];
}
void H_31(double *state, double *unused, double *out_3783431272122414454) {
   out_3783431272122414454[0] = 0;
   out_3783431272122414454[1] = 0;
   out_3783431272122414454[2] = 0;
   out_3783431272122414454[3] = 0;
   out_3783431272122414454[4] = 0;
   out_3783431272122414454[5] = 0;
   out_3783431272122414454[6] = 0;
   out_3783431272122414454[7] = 0;
   out_3783431272122414454[8] = 1;
}
#include <eigen3/Eigen/Dense>
#include <iostream>

typedef Eigen::Matrix<double, DIM, DIM, Eigen::RowMajor> DDM;
typedef Eigen::Matrix<double, EDIM, EDIM, Eigen::RowMajor> EEM;
typedef Eigen::Matrix<double, DIM, EDIM, Eigen::RowMajor> DEM;

void predict(double *in_x, double *in_P, double *in_Q, double dt) {
  typedef Eigen::Matrix<double, MEDIM, MEDIM, Eigen::RowMajor> RRM;

  double nx[DIM] = {0};
  double in_F[EDIM*EDIM] = {0};

  // functions from sympy
  f_fun(in_x, dt, nx);
  F_fun(in_x, dt, in_F);


  EEM F(in_F);
  EEM P(in_P);
  EEM Q(in_Q);

  RRM F_main = F.topLeftCorner(MEDIM, MEDIM);
  P.topLeftCorner(MEDIM, MEDIM) = (F_main * P.topLeftCorner(MEDIM, MEDIM)) * F_main.transpose();
  P.topRightCorner(MEDIM, EDIM - MEDIM) = F_main * P.topRightCorner(MEDIM, EDIM - MEDIM);
  P.bottomLeftCorner(EDIM - MEDIM, MEDIM) = P.bottomLeftCorner(EDIM - MEDIM, MEDIM) * F_main.transpose();

  P = P + dt*Q;

  // copy out state
  memcpy(in_x, nx, DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
}

// note: extra_args dim only correct when null space projecting
// otherwise 1
template <int ZDIM, int EADIM, bool MAHA_TEST>
void update(double *in_x, double *in_P, Hfun h_fun, Hfun H_fun, Hfun Hea_fun, double *in_z, double *in_R, double *in_ea, double MAHA_THRESHOLD) {
  typedef Eigen::Matrix<double, ZDIM, ZDIM, Eigen::RowMajor> ZZM;
  typedef Eigen::Matrix<double, ZDIM, DIM, Eigen::RowMajor> ZDM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, EDIM, Eigen::RowMajor> XEM;
  //typedef Eigen::Matrix<double, EDIM, ZDIM, Eigen::RowMajor> EZM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, 1> X1M;
  typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> XXM;

  double in_hx[ZDIM] = {0};
  double in_H[ZDIM * DIM] = {0};
  double in_H_mod[EDIM * DIM] = {0};
  double delta_x[EDIM] = {0};
  double x_new[DIM] = {0};


  // state x, P
  Eigen::Matrix<double, ZDIM, 1> z(in_z);
  EEM P(in_P);
  ZZM pre_R(in_R);

  // functions from sympy
  h_fun(in_x, in_ea, in_hx);
  H_fun(in_x, in_ea, in_H);
  ZDM pre_H(in_H);

  // get y (y = z - hx)
  Eigen::Matrix<double, ZDIM, 1> pre_y(in_hx); pre_y = z - pre_y;
  X1M y; XXM H; XXM R;
  if (Hea_fun){
    typedef Eigen::Matrix<double, ZDIM, EADIM, Eigen::RowMajor> ZAM;
    double in_Hea[ZDIM * EADIM] = {0};
    Hea_fun(in_x, in_ea, in_Hea);
    ZAM Hea(in_Hea);
    XXM A = Hea.transpose().fullPivLu().kernel();


    y = A.transpose() * pre_y;
    H = A.transpose() * pre_H;
    R = A.transpose() * pre_R * A;
  } else {
    y = pre_y;
    H = pre_H;
    R = pre_R;
  }
  // get modified H
  H_mod_fun(in_x, in_H_mod);
  DEM H_mod(in_H_mod);
  XEM H_err = H * H_mod;

  // Do mahalobis distance test
  if (MAHA_TEST){
    XXM a = (H_err * P * H_err.transpose() + R).inverse();
    double maha_dist = y.transpose() * a * y;
    if (maha_dist > MAHA_THRESHOLD){
      R = 1.0e16 * R;
    }
  }

  // Outlier resilient weighting
  double weight = 1;//(1.5)/(1 + y.squaredNorm()/R.sum());

  // kalman gains and I_KH
  XXM S = ((H_err * P) * H_err.transpose()) + R/weight;
  XEM KT = S.fullPivLu().solve(H_err * P.transpose());
  //EZM K = KT.transpose(); TODO: WHY DOES THIS NOT COMPILE?
  //EZM K = S.fullPivLu().solve(H_err * P.transpose()).transpose();
  //std::cout << "Here is the matrix rot:\n" << K << std::endl;
  EEM I_KH = Eigen::Matrix<double, EDIM, EDIM>::Identity() - (KT.transpose() * H_err);

  // update state by injecting dx
  Eigen::Matrix<double, EDIM, 1> dx(delta_x);
  dx  = (KT.transpose() * y);
  memcpy(delta_x, dx.data(), EDIM * sizeof(double));
  err_fun(in_x, delta_x, x_new);
  Eigen::Matrix<double, DIM, 1> x(x_new);

  // update cov
  P = ((I_KH * P) * I_KH.transpose()) + ((KT.transpose() * R) * KT);

  // copy out state
  memcpy(in_x, x.data(), DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
  memcpy(in_z, y.data(), y.rows() * sizeof(double));
}




}
extern "C" {

void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_25, H_25, NULL, in_z, in_R, in_ea, MAHA_THRESH_25);
}
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<2, 3, 0>(in_x, in_P, h_24, H_24, NULL, in_z, in_R, in_ea, MAHA_THRESH_24);
}
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_30, H_30, NULL, in_z, in_R, in_ea, MAHA_THRESH_30);
}
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_26, H_26, NULL, in_z, in_R, in_ea, MAHA_THRESH_26);
}
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_27, H_27, NULL, in_z, in_R, in_ea, MAHA_THRESH_27);
}
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_29, H_29, NULL, in_z, in_R, in_ea, MAHA_THRESH_29);
}
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_28, H_28, NULL, in_z, in_R, in_ea, MAHA_THRESH_28);
}
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_31, H_31, NULL, in_z, in_R, in_ea, MAHA_THRESH_31);
}
void car_err_fun(double *nom_x, double *delta_x, double *out_4525121693915560921) {
  err_fun(nom_x, delta_x, out_4525121693915560921);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_1972415448394742236) {
  inv_err_fun(nom_x, true_x, out_1972415448394742236);
}
void car_H_mod_fun(double *state, double *out_7275833948890819174) {
  H_mod_fun(state, out_7275833948890819174);
}
void car_f_fun(double *state, double dt, double *out_7956715178949728761) {
  f_fun(state,  dt, out_7956715178949728761);
}
void car_F_fun(double *state, double dt, double *out_4817379664253254158) {
  F_fun(state,  dt, out_4817379664253254158);
}
void car_h_25(double *state, double *unused, double *out_147038242079145023) {
  h_25(state, unused, out_147038242079145023);
}
void car_H_25(double *state, double *unused, double *out_8151142693229822154) {
  H_25(state, unused, out_8151142693229822154);
}
void car_h_24(double *state, double *unused, double *out_4380945631886811145) {
  h_24(state, unused, out_4380945631886811145);
}
void car_H_24(double *state, double *unused, double *out_6737675781677406326) {
  H_24(state, unused, out_6737675781677406326);
}
void car_h_30(double *state, double *unused, double *out_3784487770333167373) {
  h_30(state, unused, out_3784487770333167373);
}
void car_H_30(double *state, double *unused, double *out_7777268421972480835) {
  H_30(state, unused, out_7777268421972480835);
}
void car_h_26(double *state, double *unused, double *out_1858242100747789462) {
  h_26(state, unused, out_1858242100747789462);
}
void car_H_26(double *state, double *unused, double *out_4409639374355765930) {
  H_26(state, unused, out_4409639374355765930);
}
void car_h_27(double *state, double *unused, double *out_8970756540361744684) {
  h_27(state, unused, out_8970756540361744684);
}
void car_H_27(double *state, double *unused, double *out_8494712339936645870) {
  H_27(state, unused, out_8494712339936645870);
}
void car_h_29(double *state, double *unused, double *out_8786161037994013018) {
  h_29(state, unused, out_8786161037994013018);
}
void car_H_29(double *state, double *unused, double *out_7267037077658088651) {
  H_29(state, unused, out_7267037077658088651);
}
void car_h_28(double *state, double *unused, double *out_3833257662266850097) {
  h_28(state, unused, out_3833257662266850097);
}
void car_H_28(double *state, double *unused, double *out_6097307978981932391) {
  H_28(state, unused, out_6097307978981932391);
}
void car_h_31(double *state, double *unused, double *out_128155820205360866) {
  h_31(state, unused, out_128155820205360866);
}
void car_H_31(double *state, double *unused, double *out_3783431272122414454) {
  H_31(state, unused, out_3783431272122414454);
}
void car_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
void car_set_mass(double x) {
  set_mass(x);
}
void car_set_rotational_inertia(double x) {
  set_rotational_inertia(x);
}
void car_set_center_to_front(double x) {
  set_center_to_front(x);
}
void car_set_center_to_rear(double x) {
  set_center_to_rear(x);
}
void car_set_stiffness_front(double x) {
  set_stiffness_front(x);
}
void car_set_stiffness_rear(double x) {
  set_stiffness_rear(x);
}
}

const EKF car = {
  .name = "car",
  .kinds = { 25, 24, 30, 26, 27, 29, 28, 31 },
  .feature_kinds = {  },
  .f_fun = car_f_fun,
  .F_fun = car_F_fun,
  .err_fun = car_err_fun,
  .inv_err_fun = car_inv_err_fun,
  .H_mod_fun = car_H_mod_fun,
  .predict = car_predict,
  .hs = {
    { 25, car_h_25 },
    { 24, car_h_24 },
    { 30, car_h_30 },
    { 26, car_h_26 },
    { 27, car_h_27 },
    { 29, car_h_29 },
    { 28, car_h_28 },
    { 31, car_h_31 },
  },
  .Hs = {
    { 25, car_H_25 },
    { 24, car_H_24 },
    { 30, car_H_30 },
    { 26, car_H_26 },
    { 27, car_H_27 },
    { 29, car_H_29 },
    { 28, car_H_28 },
    { 31, car_H_31 },
  },
  .updates = {
    { 25, car_update_25 },
    { 24, car_update_24 },
    { 30, car_update_30 },
    { 26, car_update_26 },
    { 27, car_update_27 },
    { 29, car_update_29 },
    { 28, car_update_28 },
    { 31, car_update_31 },
  },
  .Hes = {
  },
  .sets = {
    { "mass", car_set_mass },
    { "rotational_inertia", car_set_rotational_inertia },
    { "center_to_front", car_set_center_to_front },
    { "center_to_rear", car_set_center_to_rear },
    { "stiffness_front", car_set_stiffness_front },
    { "stiffness_rear", car_set_stiffness_rear },
  },
  .extra_routines = {
  },
};

ekf_lib_init(car)
